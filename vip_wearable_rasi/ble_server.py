import asyncio
import struct
import sys
import time
import serial
from bluez_peripheral.util import *
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags

# [GATT 사양 고정] 기존 앱 5바이트 사양과 100% 일치
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_YAW_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_ERROR_WRITE_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

YAW_TX_PERIOD_SEC = 0.05    
DISCONNECT_TIMEOUT_SEC = 2.0  # 💡 앱 패킷이 2초간 끊기면 무조건 단절로 간주

UART_PORT = "/dev/ttyS0"     
BAUDRATE = 115200

latest_stm32_yaw = 0.0
global_ser = None             
has_st_awakened = False       
last_rx_packet_time = 0.0     # 💡 앱으로부터 0x22 패킷을 마지막으로 수신한 시간

def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_ser
    if has_st_awakened:
        has_st_awakened = False
        print("\n==================================================")
        print("[시스템 시퀀스] 앱 데이터 스트림 수신 단절 최종 감지!")
        print("[대기동작 진입] ST 보드를 슬립 모드(0x00)로 리셋 조치합니다.")
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
            global_ser.flush()  # 💡 버퍼 밀림 없이 즉시 물리 전송 완료 보장
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
                
                # 💡 앱에서 정상 데이터가 들어올 때마다 타임스탬프 최신화
                last_rx_packet_time = time.time()

                if not has_st_awakened:
                    has_st_awakened = True
                    print("\n==================================================")
                    print("[BLE 이벤트] 안드로이드 앱 연동 성공! 나침반 및 통신 가동.")
                    print("==================================================")
                    if global_ser and global_ser.is_open:
                        global_ser.reset_input_buffer()
                    send_control_flag_to_stm32(0x01)

                # 실시간 각도 오차 데이터 ST 보드로 즉시 다운스트림 전송
                send_angle_error_to_stm32(angle_error)

                if angle_error != 0.0:
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"
                    print(f"[수신] 앱 경로 편차 오차: {angle_error:.1f}° -> {direction} 보정 제어 중          ", end="\n\r")
                else:
                    print("[상태] Tmap 안내 대기 중 | 실시간 나침반 스트리밍 가동 중", end="\r")
            else:
                print(f"\n[경고] 앱 통신 규격 부적합 프로토콜 유입 무효화: {value.hex()}")
        except Exception as e:
            print(f"\n[오류] 앱 패킷 디코딩 실패: {e}")

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
            # 원격 단절 에러 감지 시에도 리셋 절차 수행
            reset_hardware_to_sleep()
            
        await asyncio.sleep(YAW_TX_PERIOD_SEC)

# 💡 [핵심 가동]: 앱의 무선 상황과 무관하게 2초간 패킷 유입이 멈추면 강제로 연결을 끊고 슬립 모드로 진입시킵니다.
async def track_software_heartbeat_timeout():
    global has_st_awakened, last_rx_packet_time
    while True:
        try:
            if has_st_awakened and (time.time() - last_rx_packet_time > DISCONNECT_TIMEOUT_SEC):
                print(f"\n[하트비트 감지] 최근 {DISCONNECT_TIMEOUT_SEC}초간 앱 데이터 유입 없음 (단절 확정).")
                reset_hardware_to_sleep()
        except Exception:
            pass
        await asyncio.sleep(0.5)

async def main():
    bus = await get_message_bus()
    
    service = TrackerGattService()
    await service.register(bus)
    
    agent = Advertisement(
        "RaspberryPi4_Guide",
        [SERVICE_UUID],
        appearance=0,
        timeout=0
    )
    await agent.register(bus)
    
    print("==================================================")
    print("  라즈베리파이4 (Ubuntu 24.04) 고속 BLE 가이드 서버")
    print("==================================================")
    print("[대기] 스마트폰 어플리케이션으로부터 스캔 및 연결 바인딩을 기다립니다.")
    
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),
        track_software_heartbeat_timeout()  # 정밀 타임아웃 프로세스 가동
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[시스템] 인터럽트 시그널 감지. 가이드 서버를 안전하게 종료합니다.")
        if global_ser and global_ser.is_open:
            has_st_awakened = True
            reset_hardware_to_sleep()
            global_ser.close()
        sys.exit(0)