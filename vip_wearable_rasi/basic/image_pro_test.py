import cv2
import numpy as np
import torch
from ultralytics import YOLO
# 정리하신 3개 함수가 들어있는 파일 임포트
from basic.image_processing import detect_holes, fill_holes_with_majority, refine_boundary_with_guide

# 1. 시맨틱 세그멘테이션(segment task) 모델 로드
model_sem = YOLO("models\\best_11.pt") 

# 2. 원본 이미지 로드
img_path = "test_img/sidewalk_30.jpg"
frame_raw = cv2.imread(img_path)

if frame_raw is None:
    print(f"[오류] {img_path} 이미지를 불러올 수 없습니다.")
    exit()

# 후처리 및 최종 출력 목표 해상도 (라즈베리파이 5 최적화 크기)
TARGET_W, TARGET_H = 320, 240
# 가이드 필터용 원본 이미지 리사이즈
resized_img = cv2.resize(frame_raw, (TARGET_W, TARGET_H), interpolation=cv2.INTER_LINEAR)

# 3. YOLO 추론 수행 (작성하신 구문 그대로 적용)
results_sem = model_sem(resized_img, task="segment", imgsz=[480, 640], classes=[0,1,2], verbose=False)

# 4. 추론 결과 마스크 가공 및 후처리 연동
# 지정한 클래스(도로, 인도, 횡단보도) 중 하나라도 검출이 되었는지 확인
if results_sem[0].masks is not None:
    # (N, H, W) 형태의 바이너리 마스크 텐서 추출
    masks_tensor = results_sem[0].masks.data
    
    # 여러 개 잡힌 객체 마스크(도로, 인도 등)를 하나의 채널 마스크로 합치기
    # torch.any를 사용하여 하나라도 1인 영역은 다 포함시킵니다.
    combined_mask = torch.any(masks_tensor, dim=0).cpu().numpy().astype(np.uint8)
    
    # 5. 후처리 스케일 매칭 (320x240 리사이즈 및 0~255 변환)
    raw_mask = cv2.resize(combined_mask, (TARGET_W, TARGET_H), interpolation=cv2.INTER_NEAREST)
    raw_mask = raw_mask * 255  # 모폴로지 연산을 위해 0과 255 스케일로 확장

    # -----------------------------------------------------------------
    # 6. 정리한 3단계 후처리 함수 순차 실행
    # -----------------------------------------------------------------
    # [단계 2] 구멍 위치 찾기 (320x240 환경에 맞춰 커널 크기 다운)
    hole_mask, filled_base = detect_holes(raw_mask, kernel_size=7)
    
    # [단계 3] 주변부 참조 메꾸기
    filled_mask = fill_holes_with_majority(raw_mask, hole_mask, filled_base, median_ksize=3)
    
    # [단계 4] 가이드 필터 경계 정제 (320x240 원본 이미지 가이드 사용)
    final_mask = refine_boundary_with_guide(filled_mask, resized_img, radius=2, eps=1e-2)

    # 7. 최종 결과 시각화
    cv2.imshow("0. YOLO Original Mask", raw_mask)
    cv2.imshow("1. Refined Final Mask", final_mask)
    
    print("이미지 창을 선택하고 'q'를 누르면 프로그램이 종료됩니다.")
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()

else:
    print("[안내] 현재 프레임에서 도로, 인도, 횡단보도 클래스가 전혀 검출되지 않았습니다.")
    print("      신뢰도 임계값(conf)이 너무 높거나, 이미지 경로가 맞는지 확인해 보세요.")