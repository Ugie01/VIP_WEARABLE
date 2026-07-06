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

latest_stm32_yaw = 0.0
has_st_awakened = False
last_rx_packet_time = 0.0
global_ser = None

def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_ser
    if has_st_awakened:
        has_st_awakened = False
        print("\n==================================================")
        print("[ble_core.py] 연결 단절 조치 및 대기 모드 진입")
        print("ST 보드를 슬립 모드(0x00)로 리셋")
        print("==================================================")
        send_control_flag_to_stm32(0x00)
        config.latest_stm32_yaw = 0.0
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
            print(f"[ble_core.py] ST 보드로 {status_text} 명령 플래그({hex(flag_value)}) 전송 완료.")
        except Exception as e:
            print(f"[ble_core.py] 오류: ST 플래그 전파 실패: {e}")

def send_angle_error_to_stm32(angle_error):
    global global_ser
    if global_ser and global_ser.is_open:
        try:
            packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01])
            global_ser.write(packet)
        except Exception as e:
            print(f"[ble_core.py] 오류: ST 오차 데이터 전파 실패: {e}")

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
        global has_st_awakened, last_rx_packet_time
        try:
            if len(value) == 5 and value[0] == 0x22:
                angle_error = struct.unpack('!f', value[1:5])[0]
                last_rx_packet_time = time.time()

                if not has_st_awakened:
                    has_st_awakened = True
                    print("\n==================================================")
                    print("[ble_core.py] 앱 연동 성공")
                    print("==================================================")
                    if global_ser and global_ser.is_open:
                        global_ser.reset_input_buffer()
                    send_control_flag_to_stm32(0x01)

                send_angle_error_to_stm32(angle_error)

                if angle_error != 0.0:
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"
                    print(f"[ble_core.py] 수신: 앱 경로 편차 오차: {angle_error:.1f}° -> {direction} 보정 확인          ", end="\n\r")
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
    global latest_stm32_yaw, global_ser, has_st_awakened

    print(f"[하드웨어] STM32 수신용 UART 채널 바인딩 가동 ({config.UART_PORT}, {config.BAUDRATE}bps)")
    try:
        global_ser = serial.Serial(config.UART_PORT, baudrate=config.BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"[ble_core.py] 오류: UART 포트 개방 실패 (권한 누락 또는 장치 없음): {e}")
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
                    payload = global_ser.read(4)
                    parsed_pitch = struct.unpack('<f', payload)[0]
                    
                    if -180.0 <= parsed_yaw <= 180.0:
                        latest_stm32_yaw = parsed_yaw
                    if -180.0 <= parsed_pitch <= 180.0:
                        g.PITCH = parsed_pitch
                        
        except Exception as e:
            print(f"\n[ble_core.py] 오류: UART 통신 오류, 데이터 스트림 무효화: {e}")
            
        await asyncio.sleep(0.01)

async def send_yaw_loop(service_instance):
    global latest_stm32_yaw, has_st_awakened
    
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
    
    force_kernel_advertising()
    
    print("==================================================")
    print("라즈베리파이5 고속 BLE 가이드 서버")
    print("==================================================")
    print("[ble_core.py] 앱으로부터 스캔 및 연결 바인딩을 기다리는중")
    
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),
        track_software_heartbeat_timeout()
    )

def run_ble_server_process():
    try:
        asyncio.run(async_ble_main())
    except KeyboardInterrupt:
        print("\n[ble_core.py] BLE 서버 인터럽트 감지 및 가이드 서버 종료 중...")
        has_st_awakened = True
        reset_hardware_to_sleep()
        if global_ser and global_ser.is_open:
            global_ser.close()
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        sys.exit(0)