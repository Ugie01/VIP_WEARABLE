import glob
import os
import xml.etree.ElementTree as ET


def convert_object_xml_to_yolo(xml_path, output_dir, class_mapping):
    """오브젝트 마스킹 XML을 YOLO 세그멘테이션 TXT 포맷으로 변환하는 함수"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # XML 파일 파싱
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"❌ XML 파일을 읽는 중 오류가 발생했습니다: {e}")
        return 0

    image_count = 0

    # <image> 태그를 하나씩 순회
    for img_tag in root.findall("image"):
        img_name = img_tag.get("name")

        # 💡 파일명 중복을 피하기 위해 접두어(obj_) 추가
        txt_name = "obj_" + os.path.splitext(img_name)[0] + ".txt"
        txt_path = os.path.join(output_dir, txt_name)

        w = float(img_tag.get("width"))
        h = float(img_tag.get("height"))

        yolo_lines = []

        for poly in img_tag.findall("polygon"):
            label = poly.get("label")

            if label not in class_mapping:
                continue

            class_id = class_mapping[label]
            points_str = poly.get("points")

            if not points_str:
                continue

            yolo_points = []
            try:
                for pt in points_str.split(";"):
                    if not pt.strip():
                        continue
                    x, y = map(float, pt.split(","))

                    norm_x = min(max(x / w, 0.0), 1.0)
                    norm_y = min(max(y / h, 0.0), 1.0)

                    yolo_points.append(f"{norm_x:.6f} {norm_y:.6f}")

                if len(yolo_points) >= 3:
                    yolo_line = f"{class_id} " + " ".join(yolo_points)
                    yolo_lines.append(yolo_line)

            except Exception as e:
                print(f"⚠️ {img_name}의 {label} 좌표 파싱 중 에러 발생: {e}")
                continue

        if yolo_lines:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(yolo_lines) + "\n")
            image_count += 1

    return image_count


if __name__ == "__main__":
    # 1. 6번부터 시작하는 오브젝트 데이터 class_map 구조
    class_map = {
        "pole": 6,  # 전신주/기둥
        "person": 7,  # 사람
        "dog": 8,  # 개
        "cat": 8,  # 고양이 (동물로 통합)
        "bollard": 9,  # 볼라드
        "bicycle": 10,  # 자전거
    }

    # 2. 어디서부터 어디까지 변환할지 범위 지정
    START_NUM = 1
    END_NUM = 14  # 👈 원하는 끝 폴더 번호를 지정하세요.

    # 3. 공통 저장 폴더 경로 지정
    OUTPUT_DIR_PATH = r"D:\training_data\labels"

    total_converted_files = 0
    print(
        f"🚀 와일드카드를 이용하여 {START_NUM}번부터 {END_NUM}번 폴더까지 자동 검색 및 변환을 시작합니다...\n"
    )

    # 반복문 순회 시작
    for i in range(START_NUM, END_NUM + 1):
        # 자릿수 패딩 기법 (예: i가 1일 때 -> 'Polygon_0001')
        folder_num_str = f"{i:04d}"
        base_folder_path = f"D:\\training_data\\인도보행 영상\\폴리곤세크멘테이션\\Polygon_1_new\\Polygon_{folder_num_str}"

        print(f"📦 [{i}/{END_NUM}] 폴더 접근 중: Polygon_{folder_num_str}")

        # 💡 와일드카드 패턴 설정: 해당 폴더 내부의 모든 .xml 파일 매칭
        # 예: base_folder_path\*.xml
        search_pattern = os.path.join(base_folder_path, "*.xml")

        # 와일드카드 조건에 만족하는 실제 파일 리스트 찾기
        xml_files = glob.glob(search_pattern)

        if xml_files:
            # 매칭된 첫 번째 XML 파일을 선택 (이름 규칙이 뒤죽박죽이어도 무조건 찾아냄)
            XML_FILE_PATH = xml_files[0]
            detected_xml_name = os.path.basename(XML_FILE_PATH)

            print(f"   -> 🔍 [와일드카드 발견]: {detected_xml_name} 변환 시작")

            # 변환 작업 실행
            cnt = convert_object_xml_to_yolo(
                XML_FILE_PATH, OUTPUT_DIR_PATH, class_map
            )
            total_converted_files += cnt
            print(f"   -> 완료: {cnt}개의 이미지 정답지 생성됨.")
        else:
            print(
                f"   ❌ [파일 없음] 폴더가 없거나 내부에 .xml 확장자를 가진 파일이 존재하지 않습니다."
            )

        print("-" * 50)

    print(
        f"\n🎉 모든 작업이 끝났습니다! 총 {total_converted_files}개의 YOLO 정답지(.txt) 파일이 생성되었습니다."
    )