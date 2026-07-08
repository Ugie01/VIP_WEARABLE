# basic/g_val.py
from multiprocessing import Value

# 최초 1회 생성되어 모든 프로세스 간에 완벽히 동기화되는 전역 변수 방 개설
FRAME_OK = Value('b', False)
OD_PROCESSING = Value('b', True)
SEM_PROCESSING = Value('b', True)
OBJECT_EXIST = Value('b', False)
ANGLE_LEFT_RIGHT = Value('b', False)
ANGLE_OK = Value('b', False)
ANGLE_VALUE = Value('f', 0.0)
PITCH = Value('f', 0.0)
BLE_CONNECTED = Value('b', False) # BLE 연결 상태를 공유하는 플래그