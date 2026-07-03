import os
import xml.etree.ElementTree as ET


def convert_aihub_xml_to_yolo(xml_path, output_dir, class_mapping):
    """AI 허브 시맨틱 세그멘테이션 XML을 YOLO 세그멘테이션 TXT 포맷으로 변환하는 함수"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # XML 파일 파싱
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"❌ XML 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    image_count = 0

    # <image> 태그를 하나씩 순회
    for img_tag in root.findall("image"):
        img_name = img_tag.get("name")
        # 확장자를 제거하고 .txt 파일명 생성 (예: MP_SEL_SUR_009829.jpg -> MP_SEL_SUR_009829.txt)
        txt_name = os.path.splitext(img_name)[0] + ".txt"
        txt_path = os.path.join(output_dir, txt_name)

        # 이미지의 실제 가로, 세로 픽셀 크기 추출
        w = float(img_tag.get("width"))
        h = float(img_tag.get("height"))

        # 해당 이미지에 포함된 마스킹 라인들을 기록할 리스트
        yolo_lines = []

        # <polygon> 태그들을 하나씩 순회
        for poly in img_tag.findall("polygon"):
            label = poly.get("label")

            # 우리가 지정한 class_map에 없는 라벨은 과감히 패스
            if label not in class_mapping:
                continue

            class_id = class_mapping[label]
            points_str = poly.get("points")

            if not points_str:
                continue

            # 좌표 기록할 리스트
            yolo_points = []
            try:
                # "x1,y1;x2,y2;x3,y3..." 구조 파싱
                for pt in points_str.split(";"):
                    if not pt.strip():
                        continue
                    x, y = map(float, pt.split(","))

                    # ⚠️ 중요: YOLO는 픽셀 좌표가 아니라 0~1 사이의 상대 좌표를 사용합니다.
                    # 가로 좌표는 전체 width로, 세로 좌표는 전체 height로 나누어 정규화합니다.
                    norm_x = x / w
                    norm_y = y / h

                    # 소수점 6자리까지 포맷팅 (0~1 범위를 벗어나지 않도록 클리핑 안전장치 추가)
                    norm_x = min(max(norm_x, 0.0), 1.0)
                    norm_y = min(max(norm_y, 0.0), 1.0)

                    yolo_points.append(f"{norm_x:.6f} {norm_y:.6f}")

                # 좌표 개수가 최소 세 개 이상(다각형)이고 비어있지 않은 경우에만 기록
                if len(yolo_points) >= 3:
                    yolo_line = f"{class_id} " + " ".join(yolo_points)
                    yolo_lines.append(yolo_line)

            except Exception as e:
                print(
                    f"⚠️ {img_name}의 {label} 좌표 파싱 중 에러 발생: {e}"
                )
                continue

        # 마스킹 데이터가 하나라도 검출된 경우에만 최종 .txt 정답지 파일 생성
        if yolo_lines:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(yolo_lines) + "\n")
            image_count += 1

    print(
        f"🎉 변환 작업이 완료되었습니다! 총 {image_count}개의 YOLO 정답지(.txt) 파일 생성됨."
    )


if __name__ == "__main__":
    # 1. 💡 XML에 실제로 기록된 라벨명과 일치하도록 class_map 수정
    # 'roadway'(차도)와 'alley'(골목길)를 일반적인 '도로(0)' 클래스로 묶어 처리합니다.
    class_map = {
        "roadway": 0,
        "alley": 1,
        "sidewalk": 2,
        "bike_lane": 3,
        "caution_zone": 4,
        "braille_guide_blocks": 5,  # 필요 없다면 제외하셔도 됩니다.
    }

    # 2. 파일 및 폴더 경로 설정 (실제 환경에 맞게 수정하여 사용하세요)
    # ⚠️ 주의: .xml 확장자가 파일 경로 끝에 제대로 위치해 있는지 확인해 주세요!
    XML_FILE_PATH = r"D:\training_data\인도보행 영상\서피스마스킹\Surface_1\Surface_010\24_SM0915_10.xml"
    OUTPUT_DIR_PATH = r"D:\training_data\convert_img"

    # 변환 함수 실행
    convert_aihub_xml_to_yolo(XML_FILE_PATH, OUTPUT_DIR_PATH, class_map)