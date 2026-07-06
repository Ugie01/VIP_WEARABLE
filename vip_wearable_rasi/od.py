# od.py
import time
import cv2
from ultralytics import YOLO
import numpy as np
from multiprocessing import shared_memory
import basic.config as config
import basic.handler as handler
from utils import FPSCalculator, calculate_avoidance_direction

def run_object_detection(g_FRAME_OK, g_OD_PROCESSING, g_OBJECT_EXIST, g_ANGLE_OK):
    print("🔍 [od.py] 정적 객체 3방향 회피 AI 엔진 가동 (모듈화 완료)...")
    
    try:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
        raw_buf = shm.buf
    except FileNotFoundError:
        print(f"❌ 공유 메모리를 찾을 수 없습니다. main.py 상태를 확인하세요.")
        return

    if config.SHOW_DISPLAY:
        cv2.namedWindow("OD Watcher", cv2.WINDOW_AUTOSIZE)

    # 탐색할 정적 객체 클래스 리스트 (구조물/장애물 인덱스 지정)
    STATIC_CLASSES = [0, 1, 2]  # 0: 볼라드, 1: 사람, 2: 킥보드

    YOLO_OD_PATH = "models/Quantization_models/yolo26n.onnx"
    model = YOLO(YOLO_OD_PATH, task="detect")
    fps_calc = FPSCalculator(interval=1.0)

    # 💡 [초기값 설정]: 시작할 때 기본 상태를 3(중앙)으로 인지시킵니다.
    prev_direction = 3

    try:
        while True:
            if not g_FRAME_OK.value or not g_OD_PROCESSING.value:
                time.sleep(0.001)
                continue  # 🌟 아래의 model(frame) 주입부로 내려가지 않고 위로 돌려보냄
            
            # 공유 메모리 버퍼로부터 이미지 뷰 직접 바인딩 (Zero-Copy)
            frame = np.frombuffer(raw_buf, dtype=np.uint8)[:config.FRAME_SIZE].reshape((config.HEIGHT, config.WIDTH, config.CHANNELS))
            g_OD_PROCESSING.value = False

            results = model(frame, imgsz=[256, 320], classes=STATIC_CLASSES, verbose=False, conf=0.60, max_det=5)

            if results[0].boxes is not None and len(results[0].boxes) > 0:
                g_OBJECT_EXIST.value = True
                
                # 분리한 알고리즘 함수를 호출하여 방향과 위험도를 정밀 계산합니다.
                direction_id, total_score = calculate_avoidance_direction(
                    results[0].boxes, 
                    config.WIDTH, 
                    config.HEIGHT
                )

                # 위험도가 임계치를 넘었을 때만 조향 트리거 작동
                if total_score > 0.3:
                    if direction_id != prev_direction:
                        handler.handle_static_object_avoidance(total_score, target_id=0, direction_id=direction_id)
                        prev_direction = direction_id  # 현재 회피 방향 기록 (1: 왼쪽, 2: 오른쪽, 3: 중앙)
                else:
                    # 위험도가 존재하나 임계치 이하로 떨어지면 디폴트 상태(3: 중앙)로 전환 판단
                    if prev_direction != 3:
                        handler.handle_static_object_avoidance(total_score, target_id=0, direction_id=3)
                        prev_direction = 3
            else:
                g_OBJECT_EXIST.value = False
                
                # 💡 [핵심 수정]: 객체가 완전히 사라진(else) 순간에도 함수를 호출합니다!
                # 직전 프레임까지 회피(1 또는 2) 중이었다가 사라진 것이라면 중앙 복귀 함수를 실행합니다.
                if prev_direction != 3:
                    handler.handle_static_object_avoidance(0.0, target_id=0, direction_id=3)
                    prev_direction = 3  # 상태를 중앙으로 고정하여 중복 호출 방지

            if config.SHOW_DISPLAY:
                annotated_frame = results[0].plot()
                fps_calc.update()
                cv2.putText(annotated_frame, f"FPS: {fps_calc.get_fps():.1f}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
                cv2.imshow("OD Watcher", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): 
                    break
            else:
                fps_calc.update()
                
    except KeyboardInterrupt:
        print("\n👋 od.py 안전 종료.")
    finally:
        shm.close()
        if config.SHOW_DISPLAY:
            cv2.destroyAllWindows()