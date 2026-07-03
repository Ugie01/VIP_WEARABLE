import time
import sys
import cv2
import numpy as np
import torch
from multiprocessing import Process, shared_memory, freeze_support
import basic.config as config
import basic.g_val as g

# [자식 모듈의 메인 루프 함수 임포트][cite: 19]
from od import run_object_detection
from sem import run_segmentation

# =====================================================================
# [BLE 및 하드웨어 통신 모듈 임포트][cite: 20]
# =====================================================================
import asyncio
import struct
import subprocess
import serial
from bluez_peripheral.util import *
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags

# --- BLE 전역 상수 및 변수 선언 ---[cite: 20]
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_YAW_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_ERROR_WRITE_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

ADAPTER_INSPECT = """
<node>
  <interface name="org.bluez.Adapter1">
    <property name="Powered" type="b" access="readwrite"></property>
    <property name="Discoverable" type="b" access="readwrite"></property>
    <property name="Pairable" type="b" access="readwrite"></property>
    <property name="UUIDs" type="as" access="read"></property>
  </interface>
  <interface name="org.bluez.GattManager1">
    <method name="RegisterApplication">
      <arg direction="in" type="o"/>
      <arg direction="in" type="a{sv}"/>
    </method>
    <method name="UnregisterApplication">
      <arg direction="in" type="o"/>
    </method>
  </interface>
  <interface name="org.freedesktop.DBus.Properties"></interface>
</node>
"""

YAW_TX_PERIOD_SEC = 0.1
DISCONNECT_TIMEOUT_SEC = 2.0
UART_PORT = "/dev/ttyAMA0"
BAUDRATE = 115200

latest_stm32_yaw = 0.0
has_st_awakened = False
last_rx_packet_time = 0.0
global_ser = None
detected_adapter_index = "0"


def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_ser
    if has_st_awakened:
        has_st_awakened = False
        print("\n==================================================")
        print("[시스템 시퀀스] 연결 단절 조치 및 대기 모드 진입")
        print("[하드웨어] ST 보드를 슬립 모드(0x00)로 리셋 조치합니다.")
        print("==================================================")
        send_control_flag_to_stm32(0x00)
        latest_stm32_yaw = 0.0
        if global_ser and global_ser.is_open:
            global_ser.reset_input_buffer()

def send_control_flag_to_stm32(flag_value):
    global global_ser
    if global_ser and global_ser.is_open:
        try:
            packet = bytearray([0xAA]) + struct.pack('!f', 0.0) + bytearray([flag_value])
            global_ser.write(packet)
            global_ser.flush()
            status_text = "구동(Wake)" if flag_value == 0x01 else "대기/초기화(Sleep)"
            print(f"[하드웨어 제어] ST 보드로 {status_text} 명령 플래그({hex(flag_value)}) 전송 완료.")
        except Exception as e:
            print(f"[하드웨어 제어 오류] ST 플래그 전파 실패: {e}")

def send_angle_error_to_stm32(angle_error):
    global global_ser
    if global_ser and global_ser.is_open:
        try:
            packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01])
            global_ser.write(packet)
        except Exception as e:
            print(f"[하드웨어 제어 오류] ST 오차 데이터 전파 실패: {e}")

class TrackerGattService(Service):
    def __init__(self):
        super().__init__(SERVICE_UUID, True)
        print("[시스템] GATT 서버 서비스 스펙트럼 인스턴스 초기화 완료.")

    @characteristic(CHAR_YAW_NOTIFY_UUID, CharacteristicFlags.NOTIFY)
    def yaw_characteristic(self, options):
        return bytearray([0x11, 0x00, 0x00, 0x00, 0x00])

    @characteristic(CHAR_ERROR_WRITE_UUID, CharacteristicFlags.WRITE_WITHOUT_RESPONSE)
    def error_characteristic(self, options):
        pass

    @error_characteristic.setter
    def error_characteristic(self, value, options):
        global has_st_awakened, global_ser, last_rx_packet_time
        try:
            if len(value) == 5 and value[0] == 0x22:
                angle_error = struct.unpack('!f', value[1:5])[0]
                last_rx_packet_time = time.time()

                if not has_st_awakened:
                    has_st_awakened = True
                    print("\n==================================================")
                    print("[BLE 이벤트] 안드로이드 앱 연동 성공! 나침반 및 통신 가동.")
                    print("==================================================")
                    if global_ser and global_ser.is_open:
                        global_ser.reset_input_buffer()
                    send_control_flag_to_stm32(0x01)

                send_angle_error_to_stm32(angle_error)

                if angle_error != 0.0:
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"
                    print(f"[수신] 앱 경로 편차 오차: {angle_error:.1f}° -> {direction} 보정 확인          ", end="\n\r")
                else:
                    print("[상태] Tmap 안내 대기 중 | 실시간 나침반 스트리밍 가동 중", end="\r")
            else:
                print(f"\n[경고] 앱 통신 규격 부적합 프로토콜 유입 무효화: {value.hex()}")
        except Exception as e:
            print(f"\n[오류] 앱 패킷 디코딩 실패: {e}")

def force_kernel_advertising():
    print("[로그] 커널 레벨 BLE 광고 설정 및 강제 기동 중...")
    try:
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "le", "on"], check=True, capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "pairable", "off"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "connectable", "on"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "power", "on"], check=True, capture_output=True)
        
        subprocess.run([
            "sudo", "btmgmt", "--index", "0", "add-adv",
            "-u", "ffe0", 
            "-c",         
            "-n",         
            "1"           
        ], check=True, capture_output=True)
        
        subprocess.run(["sudo", "bluetoothctl", "system-alias", "VIP_Guide"], capture_output=True)
        print("✅ [성공] 커널 레벨 BLE 광고 송출 완벽 가동! (기기 이름: VIP_Guide)")
    except Exception as e:
        print(f"❌ [실패] 커널 광고 제어 실패: {e}")

async def read_stm32_uart_loop():
    global latest_stm32_yaw, global_ser, has_st_awakened
    print(f"[하드웨어] STM32 수신용 UART 채널 바인딩 가동 ({UART_PORT}, {BAUDRATE}bps)")
    
    try:
        global_ser = serial.Serial(UART_PORT, baudrate=BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"[하드웨어 오류] UART 포트 개방 실패 (권한 누락 또는 장치 없음): {e}")
        return

    while True:
        try:
            if not has_st_awakened:
                if global_ser.is_open and global_ser.in_waiting > 0:
                    global_ser.reset_input_buffer()
                await asyncio.sleep(0.1)
                continue

            if global_ser.is_open and global_ser.in_waiting >= 5:
                header = global_ser.read(1)
                if header == b'\xaa':
                    payload = global_ser.read(4)
                    parsed_yaw = struct.unpack('<f', payload)[0]
                    
                    if -180.0 <= parsed_yaw <= 180.0:
                        latest_stm32_yaw = parsed_yaw
                        
        except Exception as e:
            print(f"\n[UART 통신 오류] 데이터 스트림 무효화: {e}")
            
        await asyncio.sleep(0.01)

async def send_yaw_loop(service_instance):
    print(f"[가이드] {int(YAW_TX_PERIOD_SEC * 1000)}ms 주기 네이티브 방위각 스트리밍 타이머 가동.")
    global latest_stm32_yaw, has_st_awakened
    
    while True:
        try:
            if not has_st_awakened:
                await asyncio.sleep(YAW_TX_PERIOD_SEC)
                continue

            raw_packet = bytearray([0x11]) + struct.pack('!f', latest_stm32_yaw)
            packet = bytes(raw_packet)
            
            service_instance.yaw_characteristic.changed(packet)
            print(f"[송신] STM32 네이티브 방위각(Yaw) 앱 전송 중: {latest_stm32_yaw:.2f}°", end="\r")
                
        except Exception as e:
            error_type = type(e).__name__
            print(f"\n[단절 원인 분석 - 예외 발생] 송신 중 치명적 오류. ({error_type}: {e})")
            if "DBusError" in error_type or "Broken" in str(e) or "Timeout" in str(e):
                 print(" -> OS 커널 레벨 통신 파이프 파괴. (물리적 거리 이탈, 강한 전파 간섭, 혹은 BLE 버퍼 오버플로우가 원인입니다.)")
            reset_hardware_to_sleep()
            
        await asyncio.sleep(YAW_TX_PERIOD_SEC)

async def track_software_heartbeat_timeout():
    global has_st_awakened, last_rx_packet_time
    while True:
        try:
            if has_st_awakened and (time.time() - last_rx_packet_time > DISCONNECT_TIMEOUT_SEC):
                print(f"\n[단절 원인 분석 - 논리적 타임아웃] {DISCONNECT_TIMEOUT_SEC}초간 앱으로부터 응답 없음.")
                print(" -> BLE 연결은 유지되어 있으나, 안드로이드 OS의 배터리 최적화로 인해 앱이 프리징되었거나 스레드가 정지되었습니다.")
                reset_hardware_to_sleep()
        except Exception:
            pass
        await asyncio.sleep(0.5)

async def async_ble_main():
    print("[로그] 1단계: D-Bus 메시지 버스 연결 시도 중...")
    try:
        bus = await get_message_bus()
        print("✅ [성공] D-Bus 메시지 버스 연결 완료")
    except Exception as e:
        print(f"❌ [실패] D-Bus 연결 오류: {e}")
        return

    print("[로그] 2단계: /org/bluez/hci0 프록시 객체 고정 매핑 시도 중...")
    try:
        proxy = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", ADAPTER_INSPECT)
        adapter = Adapter(proxy)
        print("✅ [성공] 블루투스 어댑터(hci0) 인터페이스 매핑 완료")
    except Exception as e:
        print(f"❌ [실패] 어댑터 매핑 오류: {e}")
        return
        
    print("[로그] 3단계: GATT 서비스 스펙트럼 초기화 중...")
    service = TrackerGattService()
    
    print("[로그] 4단계: GATT 서비스 서비스 등록 시도 중...")
    try:
        await service.register(bus, adapter=adapter, path="/org/bluez/app/service")
        print("✅ [성공] GATT 데이터 통신 서비스 등록 완료")
    except Exception as e:
        print(f"❌ [실패] GATT 서비스 등록 에러: {e}")
        return
    
    force_kernel_advertising()
    
    print("==================================================")
    print("  라즈베리파이5 고속 BLE 가이드 서버")
    print("==================================================")
    print("[대기] 스마트폰 어플리케이션으로부터 스캔 및 연결 바인딩을 기다립니다.")
    
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),
        track_software_heartbeat_timeout()
    )

# 💡 병렬 백그라운드 BLE 서버 구동 진입점 래퍼
def run_ble_server_process():
    try:
        asyncio.run(async_ble_main())
    except KeyboardInterrupt:
        print("\n[시스템] BLE 서버 인터럽트 감지. 가이드 서버 종료 중...")
        global has_st_awakened, global_ser
        has_st_awakened = True
        reset_hardware_to_sleep()
        if global_ser and global_ser.is_open:
            global_ser.close()
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        sys.exit(0)

# =====================================================================
# [통합 중앙 컨트롤러 모듈 (시각 AI 엔진 파이프라인)][cite: 19]
# =====================================================================

def main():
    print("🧠 [main.py] 보행 보조 시스템 중앙 컨트롤러 가동 (Windows/Linux 공용 모드)...")
    torch.set_num_threads(1)
    
    # 1. 고속 영상 파이프라인용 커널 공유 메모리 영역 할당
    try:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME, create=True, size=config.FRAME_SIZE)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=config.VIDEO_SHM_NAME)
    
    # 공유 메모리를 NumPy 다차원 배열 구조로 매핑
    shm_array = np.ndarray((config.HEIGHT, config.WIDTH, config.CHANNELS), dtype=np.uint8, buffer=shm.buf)

    # 2. 자식 AI 엔진들 및 BLE 엔진 멀티코어 병렬 구동 시작
    print("🚀 [main.py] 자식 AI 엔진 및 통신 서버 병렬 프로세스 생성 중...")
    
    # 💡 [추가 적용] 비동기 BLE 서버를 백그라운드 프로세스로 분리 생성[cite: 19, 20]
    ble_process = Process(target=run_ble_server_process, daemon=True)
    ble_process.start()

    # Windows(spawn) 환경에서는 인자로 넘겨받은 동기화 객체를 자식이 고유하게 바인딩합니다.
    od_process = Process(
        target=run_object_detection, 
        args=(g.FRAME_OK, g.OD_PROCESSING, g.OBJECT_EXIST),
        daemon=True
    )
    sem_process = Process(
        target=run_segmentation, 
        args=(g.FRAME_OK, g.SEM_PROCESSING),
        daemon=True
    )
    
    od_process.start()
    sem_process.start()
    print("📍 AI 분석 병렬 프로세스 및 BLE 통신 서버가 백그라운드에서 정상 가동을 시작했습니다.")

    # 3. 📹 웹캠 하드웨어 인터페이스 오픈 설정
    camera_index = 0
    cap = cv2.VideoCapture(camera_index + config.CAMERA_BACKEND)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, config.CAMERA_BUFFER_SIZE)

    if not cap.isOpened():
        print(f"❌ 에러: 웹캠(Index: {camera_index})을 열 수 없습니다.")
        od_process.terminate()
        sem_process.terminate()
        ble_process.terminate()
        shm.close()
        shm.unlink()
        sys.exit(1)
        
    print("📹 웹캠 공급 라인이 연결되었습니다. 실시간 분석 연산을 시작합니다.")
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
        print("\n👋 시스템 안전 종료 신호를 수신했습니다.")
    finally:
        cap.release()
        od_process.terminate()
        sem_process.terminate()
        ble_process.terminate() # BLE 프로세스도 함께 종료
        shm.close()
        try:
            shm.unlink()
        except Exception:
            pass
        # BLE 커널 광고 찌꺼기 강제 정리
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        print("🛑 모든 공유 메모리 자원과 하드웨어 스트림을 원활하게 소거했습니다.")

# 💡 Windows 환경에서 multiprocessing을 사용하기 위해 가장 중요한 진입점 선언부입니다.
if __name__ == "__main__":
    # Windows 빌드 환경의 멀티프로세스 예외 처리를 지원합니다.
    freeze_support()
    main()