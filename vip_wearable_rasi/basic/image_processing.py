import cv2
import numpy as np

def detect_holes(raw_mask, kernel_size=7):
    """
    단계 2: 모폴로지 닫기(Closing) 및 차집합을 이용한 구멍 위치 검출
    :param raw_mask: 모델이 출력한 거친 이진 마스크 (0 또는 255)
    :param kernel_size: 메울 구멍의 최대 크기를 결정하는 커널 사이즈 (홀수)
    :return: 구멍 위치만 255로 표시된 이진 마스크 (Hole Mask)
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    
    # 구멍을 강제로 메운 베이스 생성
    filled_base = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel)
    
    # 차집합 연산으로 구멍 영역만 분리 (메운 마스크 - 원본 마스크)
    hole_mask = cv2.subtract(filled_base, raw_mask)
    
    return hole_mask, filled_base

def fill_holes_with_majority(raw_mask, hole_mask, filled_base, median_ksize=5):
    """
    단계 3: 검출된 구멍 위치에 주변부 다수결(Median) 클래스 전파
    :param raw_mask: 모델이 출력한 거친 이진 마스크
    :param hole_mask: 1단계에서 검출한 구멍 위치 마스크
    :param filled_base: 1단계에서 모폴로지로 메워진 베이스 마스크
    :param median_ksize: 주변부 정보를 참조할 미디언 필터 커널 크기 (홀수)
    :return: 내부 구멍이 주변 클래스로 메워진 마스크
    """
    # 고속 미디언 필터로 주변 클래스들의 대표값(다수결) 유도
    smoothed = cv2.medianBlur(filled_base, ksize=median_ksize)
    
    # 구멍이 있던 자리(hole_mask == 255)만 필터 결과값으로 교체
    filled_mask = np.where(hole_mask == 255, smoothed, raw_mask).astype(np.uint8)
    
    return filled_mask

def refine_boundary_with_guide(filled_mask, src_img, radius=4, eps=1e-2):
    """
    단계 4: 가이드 필터를 이용한 최종 외곽선 정제 및 이진화
    :param filled_mask: 2단계에서 구멍이 메워진 마스크
    :param src_img: 엣지 정보를 참조할 가이드 원본 이미지 (BGR 또는 Gray)
    :param radius: 가이드 필터 반경
    :param eps: 가이드 필터 정규화 매개변수 (엣지 선명도)
    :return: 최종 정제 완료된 이진 마스크 (0 또는 255)
    """
    # 원본 이미지의 엣지를 참조하여 마스크 경계 정렬
    refined_mask = cv2.ximgproc.guidedFilter(
        guide=src_img, 
        src=filled_mask, 
        radius=radius, 
        eps=eps
    )
    
    # 그라데이션 완화 및 칼 같은 이진 마스크로 최종 변환
    _, final_mask = cv2.threshold(refined_mask, 128, 255, cv2.THRESH_BINARY)
    
    return final_mask