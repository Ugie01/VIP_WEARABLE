import signal
import time
import sys
import cv2
import numpy as np
import torch
import subprocess
from multiprocessing import Process, shared_memory, freeze_support
import basic.config as config
import basic.g_val as g
from utils import process_navigation_vibration

from od import run_object_detection
from sem import run_segmentation
from basic.ble_core import reset_hardware_to_sleep, run_ble_server_process

# utils에서 가공할 타이머 콜백을 여기서 래핑하거나 직접 구현
def timer_handler(signum, frame):
    """
    OS가 config.TIMER_INTERVAL(예: 0.1초) 마다 메인 루프를 방해하지 않고 
    백그라운드에서 독립적으로 호출하는 인터럽트 함수입니다.
    """
    print(g.ANGLE_VALUE.value)
    # angle = 3.0  # g_val에 정의된 멀티프로세스 공유 변수 활용
    angle = g.ANGLE_VALUE.value  # 공유 메모리에서 현재 각도
    if angle != 0.0:
        process_navigation_vibration(angle)
    # print(f"⏰ [타이머 인터럽트] 현재 각도({current_angle}) 기준 방향 및 진동 제어 연산 중...")


def main():
    print("[main.py] 보행 보조 시스템 중앙 컨트롤러 가동 (Windows/Linux 공용 모드)...")
    torch.set_num_threads(1)
    
    # 고속 영상 파이프라인용 커널 공유 메모리 영역 할당
    try:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME, create=True, size=config.FRAME_SIZE)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
    
    # 공유 메모리를 NumPy 다차원 배열 구조로 매핑
    shm_array = np.ndarray((config.HEIGHT, config.WIDTH, config.CHANNELS), dtype=np.uint8, buffer=shm.buf)

    # 자식 AI 엔진들 및 BLE 엔진 멀티코어 병렬 구동 시작
    print("[main.py] 자식 AI 엔진 및 통신 서버 병렬 프로세스 생성 중...")
    
    # 비동기 BLE 서버를 백그라운드 프로세스로 분리 생성
    ble_process = Process(target=run_ble_server_process,args=(g.g_SERIAL,), daemon=True)
    ble_process.start()

    # Windows(spawn) 환경에서는 인자로 넘겨받은 동기화 객체를 자식이 고유하게 바인딩합니다.
    od_process = Process(
        target=run_object_detection, 
        args=(g.FRAME_OK, g.OD_PROCESSING, g.OBJECT_EXIST, g.ANGLE_OK),
        daemon=True
    )
    sem_process = Process(
        target=run_segmentation, 
        args=(g.FRAME_OK, g.SEM_PROCESSING, g.ANGLE_OK),
        daemon=True
    )
    
    od_process.start()
    sem_process.start()
    print("[main.py] AI 분석 병렬 프로세스 및 BLE 통신 서버가 백그라운드에서 정상 가동을 시작했습니다.")
    signal.signal(signal.SIGALRM, timer_handler)
    signal.setitimer(signal.ITIMER_REAL, 1.0, config.TIMER_INTERVAL)

    # 웹캠 하드웨어 인터페이스 오픈 설정
    camera_index = 0
    cap = cv2.VideoCapture(camera_index + config.CAMERA_BACKEND)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, config.CAMERA_BUFFER_SIZE)

    if not cap.isOpened():
        print(f"[main.py] 에러: 웹캠(Index: {camera_index})을 열 수 없습니다.")
        od_process.terminate()
        sem_process.terminate()
        ble_process.terminate()
        reset_hardware_to_sleep()
        shm.close()
        shm.unlink()
        sys.exit(1)
        
    print("[main.py] 웹캠 공급 라인이 연결되었습니다. 실시간 분석 연산을 시작합니다.")
    print("-" * 60)
    is_first_frame = True 

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            # 자식 AI 프로세스들이 앞선 프레임을 다 쓰고 대기 상태(False)로 돌아왔을 때 진입
            if is_first_frame or (not g.SEM_PROCESSING.value and not g.OD_PROCESSING.value):
                g.FRAME_OK.value = False

                # 웹캠 영상을 처리 규격(320x256)으로 리사이즈 후 공유 메모리에 다이렉트 덮어쓰기
                resized_frame = cv2.resize(frame, (config.WIDTH, config.HEIGHT))
                shm_array[:] = resized_frame[:]

                # 데이터 주입 완수 플래그 활성화
                g.FRAME_OK.value = True

                # 자식 프로세스들에게 작업 시작 동기화 신호 전달
                g.OD_PROCESSING.value = True
                g.SEM_PROCESSING.value = True
                is_first_frame = False
            else:
                # CPU 자원 폭주 차단
                time.sleep(0.001)   
                        
    except KeyboardInterrupt:
        print("\n[main.py] 시스템 안전 종료 신호를 수신했습니다.")
    finally:
        cap.release()
        od_process.terminate()
        sem_process.terminate()
        ble_process.terminate() # BLE 프로세스도 함께 종료
        reset_hardware_to_sleep()
        shm.close()
        try:
            shm.unlink()
        except Exception:
            pass
        # BLE 커널 광고 찌꺼기 강제 정리
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        print("[main.py] 모든 공유 메모리 자원과 하드웨어 스트림을 원활하게 소거했습니다.")

if __name__ == "__main__":
    freeze_support()
    main()