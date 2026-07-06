# od.py
import time
import cv2
from ultralytics import YOLO
import numpy as np
from multiprocessing import shared_memory
import basic.config as config
import basic.handler as handler
from utils import FPSCalculator, calculate_avoidance_direction

def run_object_detection(g_FRAME_OK, g_OD_PROCESSING, g_OBJECT_EXIST):
    print("[od.py] 정적 객체 3방향 회피 AI 엔진 가동 (모듈화 완료)...")
    
    try:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
        raw_buf = shm.buf
    except FileNotFoundError:
        print("[od.py] 공유 메모리를 찾을 수 없습니다. main.py 상태를 확인하세요.")
        return

    if config.SHOW_DISPLAY:
        cv2.namedWindow("OD Watcher", cv2.WINDOW_AUTOSIZE)

    # 탐색할 정적 객체 클래스 리스트 (구조물/장애물 인덱스 지정)
    STATIC_CLASSES = [0, 1, 2]  # 0: 볼라드, 1: 사람, 2: 킥보드

    YOLO_OD_PATH = "models/Quantization_models/yolo26n.onnx"
    model = YOLO(YOLO_OD_PATH, task="detect")
    fps_calc = FPSCalculator(interval=1.0)

    try:
        while True:
            if not g_FRAME_OK.value or not g_OD_PROCESSING.value:
                time.sleep(0.001)
                continue
            
            # 공유 메모리 버퍼로부터 이미지 뷰 직접 바인딩 (Zero-Copy)
            frame = np.frombuffer(raw_buf, dtype=np.uint8)[:config.FRAME_SIZE].reshape((config.HEIGHT, config.WIDTH, config.CHANNELS))
            g_OD_PROCESSING.value = False

            results = model(
                frame, 
                imgsz=[256, 320], 
                classes=STATIC_CLASSES, 
                verbose=False,
                conf=0.60,
                max_det=5,               # 동시에 최대 5개의 정적 장애물 스캔
            )
            """
            단일객체 회피 알고리즘 (기존)
            """
            # if results[0].boxes is not None and len(results[0].boxes) > 0:
            #     g_OBJECT_EXIST.value = True
            #     for box in results[0].boxes:
            #         x1, y1, x2, y2 = box.xyxy[0]
            #         box_width, box_height = x2 - x1, y2 - y1
            #         area_ratio = (box_width * box_height) / (config.WIDTH * config.HEIGHT)
                    
            #         if area_ratio > 0.8:
            #             left_area = x1 * config.HEIGHT
            #             right_area = (config.WIDTH - x2) * config.HEIGHT
            #             direction_id = 2 if left_area > right_area else 1
            #             handler.handle_static_object_avoidance(area_ratio, target_id=0, direction_id=direction_id)
            # else:
            #     g_OBJECT_EXIST.value = False

            if results[0].boxes is not None and len(results[0].boxes) > 0:
                g_OBJECT_EXIST.value = True
                
                # 분리한 알고리즘 함수를 호출하여 방향과 위험도를 정밀 계산합니다.
                direction_id, total_score = calculate_avoidance_direction(
                    results[0].boxes, 
                    config.WIDTH, 
                    config.HEIGHT
                )

                # 위험도가 임계치를 넘었을 때만 핸들러를 호출하도록 함수 바깥에서 유연하게 제어
                if total_score > 0.3:
                    handler.handle_static_object_avoidance(total_score, target_id=0, direction_id=direction_id)
            else:
                g_OBJECT_EXIST.value = False

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
        print("\n[od.py] od.py 안전 종료.")
    finally:
        shm.close()
        if config.SHOW_DISPLAY:
            cv2.destroyAllWindows()