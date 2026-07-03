# basic/config.py
import struct

# OS 공용 영상 공유 메모리 설정
VIDEO_SHM_NAME = "assist_video_shm"
WIDTH = 320
HEIGHT = 256
CHANNELS = 3
FRAME_SIZE = WIDTH * HEIGHT * CHANNELS

# 💡 [라즈베리 파이 필수 추가]: 카메라 백엔드 및 버퍼 설정
# 리눅스(라즈베리 파이 5) 표준 백엔드는 0 또는 cv2.CAP_V4L2를 사용합니다.
CAMERA_BACKEND = 0  
CAMERA_BUFFER_SIZE = 1  # 동기분이 알려준 실시간 버퍼 크기 1로 고정

# 바이너리 패킷 설정 (7바이트)
PACKET_FORMAT = "!BfBB"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

# [Linux 전용] 파이프 경로
PIPE_PATH = "/tmp/assist_event_pipe"

# [Windows 전용] 소켓 설정
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 9999

# 🚀 [성능 개선 추가] GUI 디스플레이 여부 설정 (실제 라즈베리 파이 가동 시 False로 변경)
SHOW_DISPLAY = True