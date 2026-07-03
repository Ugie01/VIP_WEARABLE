# basic/ipc_manager.py

import os
import sys  
import struct
import socket
import numpy as np
from multiprocessing import shared_memory, resource_tracker
import basic.config as config  # 💡 절대 그냥 config가 아니라 'basic.config' 여야 합니다!
import basic.handler as handler

# ==============================================================================
# 🧠 1. 메인 프로세스 전용 매니저 (Server 측: 영상 공급 & 파이프/소켓 이벤트 수신)
# ==============================================================================
class IPCManager:
    def __init__(self):
        self.shm = None
        self.shm_array = None
        self.is_linux = sys.platform.startswith('linux')
        self.server_socket = None
        
    def init_pipe(self):
        """OS를 감지하여 윈도우면 소켓 서버, 리눅스면 네임드 파이프를 자동 개통"""
        if self.is_linux:
            if os.path.exists(config.PIPE_PATH):
                os.remove(config.PIPE_PATH)
            os.mkfifo(config.PIPE_PATH)
            print(f"📍 [Linux] 네임드 파이프 개통 완료: {config.PIPE_PATH}")
        else:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((config.SOCKET_HOST, config.SOCKET_PORT))
            self.server_socket.listen(5)
            print(f"📍 [Windows] 테스트용 로컬 소켓 서버 개통 완료 (Port: {config.SOCKET_PORT})")

    def init_shared_memory(self):
        """영상 공유 메모리 할당 및 NumPy 덮어쓰기 판 매핑"""
        try:
            self.shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME, create=True, size=config.FRAME_SIZE)
        except FileExistsError:
            self.shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
        
        if self.is_linux:
            try: 
                resource_tracker.unregister(self.shm._name, "shared_memory")
            except Exception: 
                pass
            
        self.shm_array = np.ndarray((config.HEIGHT, config.WIDTH, config.CHANNELS), dtype=np.uint8, buffer=self.shm.buf)
        return self.shm_array

    def listen_pipe_stream(self):
        """OS 환경에 맞춰 분기하여 자식들의 7바이트 이벤트 스트림 감시 (스레드 구동용)"""
        if self.is_linux:
            self._listen_linux_pipe()
        else:
            self._listen_windows_socket()

    def _listen_linux_pipe(self):
        while True:
            try:
                with open(config.PIPE_PATH, "rb") as fifo:
                    while True:
                        payload = fifo.read(config.PACKET_SIZE)
                        if len(payload) < config.PACKET_SIZE: break
                        self._process_payload(payload)
            except Exception:
                import time; time.sleep(0.1)

    def _listen_windows_socket(self):
        while True:
            try:
                client_socket, _ = self.server_socket.accept()
                while True:
                    payload = client_socket.recv(config.PACKET_SIZE)
                    if len(payload) < config.PACKET_SIZE: break
                    self._process_payload(payload)
            except Exception:
                import time; time.sleep(0.1)

    def _process_payload(self, payload):
        """7바이트 로우 바이너리를 파이썬 변수로 역직렬화한 뒤 핸들러로 라우팅"""
        event_id, dist, target_id, direction_id = struct.unpack(config.PACKET_FORMAT, payload)
        handler.route_event(event_id, dist, target_id, direction_id)

    def cleanup(self):
        """시스템 종료 시 커널 자원 완전 반납"""
        if self.shm:
            self.shm.close()
            try: self.shm.unlink()
            except Exception: pass
        if self.is_linux:
            if os.path.exists(config.PIPE_PATH): os.remove(config.PIPE_PATH)
        else:
            if self.server_socket: self.server_socket.close()


# ==============================================================================
# 🤖 2. 자식 AI 프로세스 전용 매니저 (Client 측: 영상 수신 및 트리거 패킷 송신)
# ==============================================================================
class AIIPCManager:
    def __init__(self):
        self.shm = None
        self.shared_frame = None
        self.is_linux = sys.platform.startswith('linux')
        
        # OS별 통신 인스턴스 저장소
        self.client_socket = None
        self.fifo = None

    def connect_video_shm(self):
        """main.py가 생성해 둔 고속 영상 공유 메모리에 링크 연결 (Zero-Copy)"""
        try:
            self.shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
            self.shared_frame = np.ndarray(
                (config.HEIGHT, config.WIDTH, config.CHANNELS), 
                dtype=np.uint8, 
                buffer=self.shm.buf
            )
            return self.shared_frame
        except FileNotFoundError:
            print(f"❌ 공유 메모리({config.VIDEO_SHM_NAME})를 찾을 수 없습니다. main.py를 먼저 가동하세요.")
            return None

    def connect_event_pipe(self):
        """OS 환경에 맞춰 메인의 통신 채널에 커넥션 수립"""
        if self.is_linux:
            try:
                self.fifo = open(config.PIPE_PATH, "wb")
                return self.fifo
            except FileNotFoundError: 
                return None
        else:
            try:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((config.SOCKET_HOST, config.SOCKET_PORT))
                return self.client_socket
            except Exception: 
                return None

    def send_trigger(self, event_id, dist, target_id, direction_id):
        """위험/안내 신호 발생 시 비트필드급 효율을 위해 7바이트 바이너리로 즉시 송신"""
        packet = struct.pack(config.PACKET_FORMAT, event_id, dist, target_id, direction_id)
        try:
            if self.is_linux and self.fifo:
                self.fifo.write(packet)
                self.fifo.flush()
            elif not self.is_linux and self.client_socket:
                self.client_socket.sendall(packet)
        except Exception as e:
            print(f"⚠️ 트리거 패킷 송신 에러: {e}")

    def close(self):
        """프로세스 종료 시 통신 링크 안전하게 close"""
        if self.shm: self.shm.close()
        if self.fifo: self.fifo.close()
        if self.client_socket: self.client_socket.close()