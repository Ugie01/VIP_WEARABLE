import time
import sys
import asyncio
import struct
import subprocess
import serial
import queue
from bluez_peripheral.util import *
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags
import basic.g_val as g
import basic.config as config
from multiprocessing import Queue

latest_stm32_yaw = 0.0
has_st_awakened = False
global_serial = None

ai_tx_queue = None
def init_ai_queue(shared_queue):
    global ai_tx_queue
    ai_tx_queue = shared_queue

async def watch_ai_commands_loop():
    global global_serial, has_st_awakened
    print("[ble_core.py] AI 제어 명령 수신 태스크 가동 완료.")
    
    while True:
        try:
            if ai_tx_queue and not ai_tx_queue.empty():
                try:
                    angle_error, state = ai_tx_queue.get_nowait()
                    st = 0x01 if state else 0x00
                    
                    if global_serial and global_serial.is_open:
                        packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01]) + bytearray([st])
                        global_serial.write(packet)
                        global_serial.flush()
                except queue.Empty:
                    pass
        except Exception as e:
            print(f"[ble_core.py] AI 명령 전달 중 오류: {e}")
        await asyncio.sleep(0.02)

def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_serial
    if has_st_awakened:
        has_st_awakened = False
        
        g.BLE_CONNECTED.value = False 
        g.ANGLE_VALUE.value = 0.0
        g.ANGLE_OK.value = False
        
        print("\n==================================================")
        print("[ble_core.py] 연결 종료 명령(또는 단절) 수신! 대기 모드 진입")
        print("ST 보드를 슬립 모드(0x00)로 리셋 및 AI 비전 분석 중단")
        print("==================================================")
        send_control_flag_to_stm32(0x00)
        config.latest_stm32_yaw = 0.0
        if global_serial and global_serial.is_open:
            global_serial.reset_input_buffer()

def send_control_flag_to_stm32(flag_value):
    global global_serial
    if global_serial is None or not global_serial.is_open:
        return
    try:
        packet = bytearray([0xAA]) + struct.pack('!f', 0.0) + bytearray([flag_value]) + bytearray([0x00])
        global_serial.write(packet)
        global_serial.flush()
        status_text = "구동(Wake)" if flag_value == 0x01 else "대기/초기화(Sleep)"
        print(f"[ble_core.py] ST 보드로 {status_text} 명령 플래그 전송 완료.")
    except Exception as e:
        print(f"[ble_core.py] 오류: ST 플래그 전파 실패: {e}")

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
        global has_st_awakened, global_serial
        try:
            # 1. 🌟 상태 제어 플래그 수신부 (0x33 + 상태값 1바이트)
            if len(value) == 2 and value[0] == 0x33:
                app_state = value[1]

                if app_state == 0:
                    print("\n[ble_core.py] 📱앱 명령: 연결 종료 (Sleep)")
                    reset_hardware_to_sleep()

                elif app_state == 1:
                    print("\n==================================================")
                    print("[ble_core.py] 📱앱 명령: 연결됨/경로취소 (AI ON, 대기 중)")
                    print("==================================================")
                    g.ANGLE_VALUE.value = 0.0
                    g.ANGLE_OK.value = False
                    
                    if not has_st_awakened:
                        has_st_awakened = True
                        g.BLE_CONNECTED.value = True
                        if global_serial and global_serial.is_open:
                            global_serial.reset_input_buffer()
                        send_control_flag_to_stm32(0x01)
                    
                    # 경로 취소 시 ST 보드 조향 중립(0.0) 전송
                    if ai_tx_queue:
                        try:
                            ai_tx_queue.put_nowait((0.0, False))
                        except queue.Full:
                            pass

                elif app_state == 2:
                    print("\n[ble_core.py] 📱앱 명령: 목적지 입력! (내비게이션 시작)")
                    # 여기서 굳이 할 건 없습니다. 바로 뒤이어 0x22 방향 패킷이 날아올 것이기 때문.

            # 2. 기존 방향 제어 데이터 수신부 (0x22 + 4바이트 float)
            elif len(value) == 5 and value[0] == 0x22:
                g.ANGLE_VALUE.value = struct.unpack('!f', value[1:5])[0]
                if g.ANGLE_VALUE.value != 0.0:
                    direction = "오른쪽" if g.ANGLE_VALUE.value > 0 else "왼쪽"
                    print(f"[ble_core.py] 수신: 앱 경로 오차: {g.ANGLE_VALUE.value:.1f}° -> {direction} 보정          ", end="\r")

            else:
                pass
        except Exception as e:
            print(f"\n[ble_core.py] 오류: 앱 패킷 디코딩 실패: {e}")

def force_kernel_advertising():
    try:
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "le", "on"], check=True, capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "pairable", "off"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "connectable", "on"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "power", "on"], check=True, capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "add-adv", "-u", "ffe0", "-c", "-n", "1"], check=True, capture_output=True)
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

            if global_serial and global_serial.is_open and global_serial.in_waiting >= 9: 
                header = global_serial.read(1)
                if header == b'\xaa':
                    payload = global_serial.read(4)
                    parsed_yaw = struct.unpack('<f', payload)[0]
                    payload = global_serial.read(4)
                    parsed_pitch = struct.unpack('<f', payload)[0]
                    
                    if -180.0 <= parsed_yaw <= 180.0:
                        latest_stm32_yaw = parsed_yaw
                    if -90.0 <= parsed_pitch <= 90.0:
                        g.PITCH.value = parsed_pitch
        except Exception:
            pass
        await asyncio.sleep(0.01)

async def send_yaw_loop(service_instance):
    global latest_stm32_yaw, has_st_awakened
    print(f"[ble_core.py] {int(config.YAW_TX_PERIOD_SEC * 1000)}ms 주기 방위각 스트리밍 대기 중...")
    while True:
        try:
            if not has_st_awakened:
                await asyncio.sleep(config.YAW_TX_PERIOD_SEC)
                continue

            raw_packet = bytearray([0x11]) + struct.pack('!f', latest_stm32_yaw)
            service_instance.yaw_characteristic.changed(bytes(raw_packet))
            print(f"[ble_core.py] 송신: STM32 방위각(Yaw) 전송 중: {latest_stm32_yaw:.2f}°", end="\r")
                
        except Exception as e:
            # 일시적인 통신 딜레이나 에러가 발생해도 바로 시스템을 초기화하지 않고 무시하도록 변경.
            # (진짜로 끊어진 거면 어차피 앱이 알아채고 재연결하거나 0x00을 보냄)
            print(f"\n[ble_core.py] 경고: STM32 방위각 전송 중 오류 발생: {e}")
            pass
            
        await asyncio.sleep(config.YAW_TX_PERIOD_SEC)

async def async_ble_main():
    global global_serial
    print("[ble_core.py] D-Bus 메시지 버스 및 프록시 객체 바인딩 중...")
    try:
        bus = await get_message_bus()
        proxy = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", config.ADAPTER_INSPECT)
        adapter = Adapter(proxy)
    except Exception as e:
        print(f"[ble_core.py] 오류: BLE 어댑터 매핑 오류: {e}")
        return
        
    service = TrackerGattService()
    try:
        await service.register(bus, adapter=adapter, path="/org/bluez/app/service")
    except Exception as e:
        print(f"[ble_core.py] 오류: GATT 서비스 등록 에러: {e}")
        return
    
    print(f"[하드웨어] STM32용 UART 채널 바인딩 ({config.UART_PORT}, {config.BAUDRATE}bps)")
    try:
        global_serial = serial.Serial(config.UART_PORT, baudrate=config.BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"[ble_core.py] 오류: UART 포트 실패: {e}")
        return

    force_kernel_advertising()
    print("==================================================")
    print("라즈베리파이 고속 BLE 가이드 서버")
    print("==================================================")
    
    # 🌟 무거운 Timeout 감시 함수(bluetoothctl) 제거됨
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),
        watch_ai_commands_loop()
    )

def run_ble_server_process(shared_queue):
    global ai_tx_queue, has_st_awakened, global_serial
    ai_tx_queue = shared_queue
    try:
        asyncio.run(async_ble_main())
    except KeyboardInterrupt:
        print("\n[ble_core.py] BLE 서버 종료 중...")
        has_st_awakened = True
        reset_hardware_to_sleep()
        if global_serial and global_serial.is_open:
            global_serial.close()
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)
        sys.exit(0)