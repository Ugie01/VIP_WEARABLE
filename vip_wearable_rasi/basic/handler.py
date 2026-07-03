# basic/handler.py
import basic.g_val as g

def handle_critical_distance(val, target_id, direction_id):
    targets = {1: "볼라드", 2: "사람", 3: "킥보드"}
    directions = {1: "왼쪽", 2: "중앙", 3: "오른쪽"}
    print(f"🚨 [위험 - OD] {val:.2f}m {directions.get(direction_id, '전방')}에 [{targets.get(target_id, '장애물')}] 감지! 정지하세요.")

def handle_path_deviation(val, target_id, direction_id):
    directions = {1: "왼쪽", 2: "오른쪽", 3: "중앙"}
    if directions.get(direction_id) == "중앙":
        g.ANGLE_OK.value = True
        g.ANGLE_LEFT_RIGHT.value = False
    elif directions.get(direction_id) == "왼쪽":
        g.ANGLE_LEFT_RIGHT.value = True
        g.ANGLE_OK.value = False
    elif directions.get(direction_id) == "오른쪽":
        g.ANGLE_LEFT_RIGHT.value = False
        g.ANGLE_OK.value = False
    print(f"🔄 [경로 보정 - SEM] 보행 경로가 {directions.get(direction_id, 'unknown')}쪽으로 이탈했습니다.")

def handle_surface_changed(val, target_id, direction_id):
    surfaces = {0: "차도", 1: "보도블록", 2: "횡단보도"}
    print(f"ℹ️ [지형 안내 - SEM] 전방에 [{surfaces.get(target_id, '지형')}] 진입합니다.")

def handle_static_object_avoidance(val, target_id, direction_id):
    directions = {1: "왼쪽", 2: "오른쪽", 3: "중앙"}
    print(f"⚠️ [정적 장애물 회피 - OD] 전방에 정적 장애물 감지! {directions.get(direction_id, 'NONE')}으로 회피하세요.")