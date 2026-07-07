import time
import sys
import asyncio
import struct
import subprocess
import serial
from bluez_peripheral.util import *
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags
import basic.g_val as g
import basic.config as config
from multiprocessing import Queue

latest_stm32_yaw = 0.0
has_st_awakened = False
last_rx_packet_time = 0.0
global_serial = None

# 메인 프로세스로부터 데이터를 받을 공용 큐 변수
ai_tx_queue = None
def init_ai_queue(shared_queue):
    global ai_tx_queue
    ai_tx_queue = shared_queue

async def watch_ai_commands_loop():
    """메인(AI) 프로세스가 큐에 넣은 조향 명령을 감시하다가 발견하면 STM32로 전송"""
    global global_serial, has_st_awakened
    print("[ble_core.py] AI 제어 명령 수신 태스크 가동 완료.")
    
    while True:
        try:
            # 큐에 데이터가 있는지 비동기적으로 확인 (블로킹 방지)
            if ai_tx_queue and not ai_tx_queue.empty():
                # [0]: 0xAA (헤더)
                # [1:5]: angle_error (4바이트 float)
                # [5]: cmd_flag (1바이트)
                # [6]: fb_flag (1바이트)
                angle_error, state = ai_tx_queue.get_nowait()
                st = 0x01 if state else 0x00
                
                if global_serial and global_serial.is_open:
                    packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01]) + bytearray([st])
                    global_serial.write(packet)
                    global_serial.flush()
        except Exception as e:
            print(f"[ble_core.py] AI 명령 전달 중 오류: {e}")
            
        await asyncio.sleep(0.02) # 20ms 간격 체킹

def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_serial
    if has_st_awakened:
        has_st_awakened = False
        print("\n==================================================")
        print("[ble_core.py] 연결 단절 조치 및 대기 모드 진입")
        print("ST 보드를 슬립 모드(0x00)로 리셋")
        print("==================================================")
        send_control_flag_to_stm32(0x00)
        config.latest_stm32_yaw = 0.0
        if global_serial and global_serial.is_open:
            global_serial.reset_input_buffer()

def send_control_flag_to_stm32(flag_value):
    global global_serial
    # 방어 코드: 포트가 준비되지 않았으면 전송 불가
    if global_serial is None or not global_serial.is_open:
        print("[ble_core.py] 오류: 시리얼 포트가 준비되지 않아 제어 플래그를 전송할 수 없습니다.")
        return

    try:
        packet = bytearray([0xAA]) + struct.pack('!f', 0.0) + bytearray([flag_value]) + bytearray([0x00])
        global_serial.write(packet)
        global_serial.flush()
        status_text = "구동(Wake)" if flag_value == 0x01 else "대기/초기화(Sleep)"
        print(f"[ble_core.py] ST 보드로 {status_text} 명령 플래그({hex(flag_value)}) 전송 완료.")
    except Exception as e:
        print(f"[ble_core.py] 오류: ST 플래그 전파 실패: {e}")

def send_angle_error_to_stm32(angle_error, state):
    global global_serial, has_st_awakened
    
    # 방어 코드 1: 객체 None 체크 및 오픈 여부 확인 (에러 차단)
    if global_serial is None or not global_serial.is_open:
        print("[하드웨어 제어 오류] 시리얼 포트가 연결되지 않은 상태입니다.")
        return

    # 방어 코드 2: 보드 활성화 여부 확인
    if not has_st_awakened:
        global_serial.reset_input_buffer()
        print("[ble_core.py] 경고: ST 보드가 활성화되지 않은 상태에서 오차 전송 시도. 무시합니다.")
        return

    try:
        packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01]) + bytearray([state])
        global_serial.write(packet)
        global_serial.flush()
    except Exception as e:
        print(f"[하드웨어 제어 오류] ST 오차 데이터 전파 실패: {e}")

class TrackerGattService(Service):
    def __init__(self):
        super().__init__(config.SERVICE_UUID, True)
        print("[시스템] GATT 서버 서비스 스펙트럼 인스턴스 초기화 완료.")

    @characteristic(config.CHAR_YAW_NOTIFY_UUID, CharacteristicFlags.NOTIFY)
    def yaw_characteristic(self, options):
        return bytearray([0x11, 0x00, 0x00, 0x00, 0x00])

    @characteristic(config.CHAR_ERROR_WRITE_UUID, CharacteristicFlags.WRITE_WITHOUT_RESPONSE)
    def error_characteristic(self, options):
        pass

    @error_characteristic.setter
    def error_characteristic(self, value, options):
        global has_st_awakened, last_rx_packet_time, global_serial
        try:
            if len(value) == 5 and value[0] == 0x22:
                g.ANGLE_VALUE.value = struct.unpack('!f', value[1:5])[0]
                last_rx_packet_time = time.time()

                if not has_st_awakened:
                    has_st_awakened = True
                    print("\n==================================================")
                    print("[ble_core.py] 앱 연동 성공")
                    print("==================================================")
                    if global_serial and global_serial.is_open:
                        global_serial.reset_input_buffer()
                    send_control_flag_to_stm32(0x01)

                if g.ANGLE_VALUE.value != 0.0:
                    direction = "오른쪽" if g.ANGLE_VALUE.value > 0 else "왼쪽"
                    print(f"[ble_core.py] 수신: 앱 경로 편차 오차: {g.ANGLE_VALUE.value:.1f}° -> {direction} 보정 확인          ", end="\n\r")
            else:
                print(f"\n[ble_core.py] 경고: 앱 통신 규격 부적합 프로토콜 유입 무효화: {value.hex()}")
        except Exception as e:
            print(f"\n[ble_core.py] 오류: 앱 패킷 디코딩 실패: {e}")

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
        print("[ble_core.py] BLE 광고 송출 성공 (기기 이름: VIP_Guide)")
    except Exception as e:
        print(f"[ble_core.py] BLE 광고 송출 실패: {e}")

async def read_stm32_uart_loop():
    global latest_stm32_yaw, has_st_awakened, global_serial

    while True:
        try:
            if not has_st_awakened:
                if global_serial and global_serial.is_open and global_serial.in_waiting > 0:
                    global_serial.reset_input_buffer()
                await asyncio.sleep(0.1)
                continue

            if global_serial and global_serial.is_open and global_serial.in_waiting >= 9: # 1(Header) + 4(Yaw) + 4(Pitch) = 총 9바이트 대기 확인
                header = global_serial.read(1)
                if header == b'\xaa':
                    payload = global_serial.read(4)
                    parsed_yaw = struct.unpack('<f', payload)[0]
                    payload = global_serial.read(4)
                    parsed_pitch = struct.unpack('<f', payload)[0]
                    
                    if -180.0 <= parsed_yaw <= 180.0:
                        latest_stm32_yaw = parsed_yaw
                    if -90.0 <= parsed_pitch <= 90.0:
                        g.PITCH = parsed_pitch
                        
        except Exception as e:
            print(f"\n[ble_core.py] 오류: UART 통신 오류, 데이터 스트림 무효화: {e}")
            
        await asyncio.sleep(0.01)

async def send_yaw_loop(service_instance):
    global latest_stm32_yaw, has_st_awakened, global_serial
    
    print(f"[ble_core.py] {int(config.YAW_TX_PERIOD_SEC * 1000)}ms 주기 네이티브 방위각 스트리밍 타이머 가동")
    while True:
        try:
            if not has_st_awakened:
                await asyncio.sleep(config.YAW_TX_PERIOD_SEC)
                continue

            raw_packet = bytearray([0x11]) + struct.pack('!f', latest_stm32_yaw)
            packet = bytes(raw_packet)
            
            service_instance.yaw_characteristic.changed(packet)
            print(f"[ble_core.py] 송신: STM32 네이티브 방위각(Yaw) 앱 전송 중: {latest_stm32_yaw:.2f}°", end="\r")
                
        except Exception as e:
            error_type = type(e).__name__
            print(f"\n[ble_core.py] 오류: 송신 중 오류 -> ({error_type}: {e})")
            if "DBusError" in error_type or "Broken" in str(e) or "Timeout" in str(e):
                 print(" -> OS 커널 레벨 통신 파이프 파괴. (물리적 거리 이탈, 강한 전파 간섭, 혹은 BLE 버퍼 오버플로우가 원인입니다.)")
            reset_hardware_to_sleep()
            
        await asyncio.sleep(config.YAW_TX_PERIOD_SEC)

async def track_software_heartbeat_timeout():
    global has_st_awakened, last_rx_packet_time
    while True:
        try:
            if has_st_awakened and (time.time() - last_rx_packet_time > config.DISCONNECT_TIMEOUT_SEC):
                print(f"\n[ble_core.py] 오류: 타임아웃 -> {config.DISCONNECT_TIMEOUT_SEC}초간 앱으로부터 응답 없음.")
                reset_hardware_to_sleep()
        except Exception:
            pass
        await asyncio.sleep(0.5)

async def async_ble_main():
    global global_serial
    print("[ble_core.py] 1단계: D-Bus 메시지 버스 연결 시도 중...")
    try:
        bus = await get_message_bus()
        print("[ble_core.py] D-Bus 메시지 버스 연결 완료")
    except Exception as e:
        print(f"[ble_core.py] 오류: D-Bus 연결 오류: {e}")
        return

    print("[ble_core.py] 2단계: /org/bluez/hci0 프록시 객체 고정 매핑 시도 중...")
    try:
        proxy = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", config.ADAPTER_INSPECT)
        adapter = Adapter(proxy)
        print("[ble_core.py] 블루투스 어댑터(hci0) 인터페이스 매핑 완료")
    except Exception as e:
        print(f"[ble_core.py] 오류: 어댑터 매핑 오류: {e}")
        return
        
    print("[ble_core.py] 3단계: GATT 서비스 스펙트럼 초기화 중...")
    service = TrackerGattService()
    
    print("[ble_core.py] 4단계: GATT 서비스 서비스 등록 시도 중...")
    try:
        await service.register(bus, adapter=adapter, path="/org/bluez/app/service")
        print("[ble_core.py] GATT 데이터 통신 서비스 등록 완료")
    except Exception as e:
        print(f"[ble_core.py] 오류: GATT 서비스 등록 에러: {e}")
        return
    
    # [수정] BLE 이벤트가 돌기 전에 시리얼 포트를 선제적으로 확실히 개방
    print(f"[하드웨어] STM32용 UART 채널 바인딩 가동 ({config.UART_PORT}, {config.BAUDRATE}bps)")
    try:
        global_serial = serial.Serial(config.UART_PORT, baudrate=config.BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"[ble_core.py] 오류: UART 포트 개방 실패: {e}")
        return

    force_kernel_advertising()
    
    print("==================================================")
    print("라즈베리파이5 고속 BLE 가이드 서버")
    print("==================================================")
    print("[ble_core.py] 앱으로부터 스캔 및 연결 바인딩을 기다리는중")
    
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),
        track_software_heartbeat_timeout(),
        watch_ai_commands_loop()
    )

def run_ble_server_process(shared_queue):
    global ai_tx_queue, has_st_awakened, global_serial
    ai_tx_queue = shared_queue
    try:
        asyncio.run(async_ble_main())
    except KeyboardInterrupt:
        print("\n[ble_core.py] BLE 서버 인터럽트 감지 및 가이드 서버 종료 중...")
        has_st_awakened = True
        reset_hardware_to_sleep()
        if global_serial and global_serial.is_open:
            global_serial.close()
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        sys.exit(0)