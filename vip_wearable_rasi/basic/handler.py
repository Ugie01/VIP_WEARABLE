# basic/handler.py 전체 수정본
import basic.g_val as g

# 전역 큐 참조 변수
tx_queue = None

def init_handler_queue(shared_queue):
    global tx_queue
    tx_queue = shared_queue

def handle_path_deviation(val, target_id, direction_id):
    global tx_queue
    directions = {1: "왼쪽", 2: "오른쪽", 3: "중앙"}
    
    if directions.get(direction_id) == "중앙":
        g.ANGLE_OK.value = True
        # 중앙일 때도 0.0 데이터를 STM32에 던져주어야 대기를 해제함
        if tx_queue is not None:
            tx_queue.put((0.0, g.ANGLE_OK.value)) # (각도, 상태)
    else:
        g.ANGLE_OK.value = False
        # 🚨 [수정] 직접 시리얼 쓰지 않고 큐에 패킷 데이터용 매개변수 투하
        if tx_queue is not None:
            tx_queue.put((val, g.ANGLE_OK.value))
            
    print(f"🔄 [경로 보정 - SEM] 보행 경로가 {directions.get(direction_id, 'unknown')}쪽으로 이탈했습니다.")

def handle_surface_changed(val, target_id, direction_id):
    surfaces = {0: "차도", 1: "보도블록", 2: "횡단보도"}
    print(f"ℹ️ [지형 안내 - SEM] 전방에 [{surfaces.get(target_id, '지형')}] 진입합니다.")

def handle_static_object_avoidance(val, target_id, direction_id):
    global tx_queue
    directions = {1: "왼쪽", 2: "오른쪽", 3: "중앙"}
    
    # 🚨 [수정] 직접 시리얼 쓰지 않고 큐에 투하
    if tx_queue is not None:
        tx_queue.put((val, g.ANGLE_OK.value))
        
    print(f"⚠️ [정적 장애물 회피 - OD] 전방에 정적 장애물 감지! {directions.get(direction_id, 'NONE')}으로 회피하세요.")