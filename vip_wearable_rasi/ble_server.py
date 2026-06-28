import asyncio
import struct
import sys
import serial  # pip install pyserial 필요
from bluez_peripheral.util import *
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags

# GATT 통신용 고유 서비스 및 캐릭터리스틱 UUID 설정
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_YAW_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_ERROR_WRITE_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

# [하이퍼파라미터] 데이터 주기 제어 선언 (단위: 초)
YAW_TX_PERIOD_SEC = 0.05    # 라즈베리파이 -> 안드로이드 앱 (50ms 주기 송신)

# [하드웨어 설정] 라즈베리파이 고유 UART 포트 및 보레이트 지정
UART_PORT = "/dev/ttyS0"     # GPIO 14, 15번 핀 (라파 모델 및 설정에 따라 /dev/ttyAMA0 일 수 있음)
BAUDRATE = 115200

# 전역 공유용 데이터 필드 (STM32 수신 루프가 이를 실시간 업데이트함)
latest_stm32_yaw = 0.0

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
        try:
            if len(value) == 5 and value[0] == 0x22:
                angle_error = struct.unpack('!f', value[1:5])[0]
                
                if angle_error == 0.0:
                    print(f"\n[수신] 경로 편차 오차: {angle_error:.1f}° -> 중심 정렬 주행 중")
                else:
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"
                    print(f"\n[수신] 경로 편차 오차: {angle_error:.1f}° -> {direction} 보정 명령 접수")
                    
                # 💡 [하드웨어 확장 포인트]: 앱에서 수신된 편차 오차 값(5바이트)을 
                # 필요하다면 STM32 보드로 다시 역전송(ser.write)하여 모터를 즉각 제어할 수도 있습니다.
                
            else:
                print(f"\n[경고] 프로토콜 포맷 결함 무효 처리: {value.hex()}")
        except Exception as e:
            print(f"\n[오류] 패킷 디코딩 실패: {e}")

# 💡 [새로 추가]: STM32 로부터 100ms마다 들어오는 UART 데이터를 백그라운드에서 읽는 독립 코루틴
async def read_stm32_uart_loop():
    global latest_stm32_yaw
    print(f"[하드웨어] STM32 수신용 UART 채널 바인딩 가동 ({UART_PORT}, {BAUDRATE}bps)")
    
    try:
        # 논블로킹 타임아웃 설정을 주어 비동기 루프와 간섭 방지
        ser = serial.Serial(UART_PORT, baudrate=BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"[하드웨어 오류] UART 포트 개방 실패 (권한 누락 또는 장치 없음): {e}")
        return

    while True:
        try:
            if ser.in_waiting >= 5: # 최소 패킷 크기(5바이트) 이상 쌓였을 때만 포킹
                header = ser.read(1)
                if header == b'\xaa': # 약속한 헤더 0xAA 매칭 가드 검증
                    payload = ser.read(4)
                    # STM32가 리틀 엔디안('<f') 또는 빅 엔디안('!f')으로 보낸 데이터 파싱
                    # (일반적으로 STM32는 리틀 엔디안 구조를 취하므로 '<f'를 기본 적용)
                    parsed_yaw = struct.unpack('<f', payload)[0]
                    
                    # 수신 범위 유효성 체크 및 전역 변수 갱신
                    if -180.0 <= parsed_yaw <= 180.0:
                        latest_stm32_yaw = parsed_yaw
                        
        except Exception as e:
            print(f"\n[UART 통신 오류] 데이터 스트림 무효화: {e}")
            
        # 10ms 단위 초고속 내부 동기화 폴링 유지
        await asyncio.sleep(0.01)

async def send_yaw_loop(service_instance):
    print(f"[가이드] {int(YAW_TX_PERIOD_SEC * 1000)}ms 주기 네이티브 방위각 스트리밍 타이머 가동.")
    global latest_stm32_yaw
    
    while True:
        try:
            # 더 이상 가짜 변동 데이터가 아니라, UART 백그라운드 루프가 채워주는 실제 최신 실시간 값을 빌드
            raw_packet = bytearray([0x11]) + struct.pack('!f', latest_stm32_yaw)
            packet = bytes(raw_packet)
            
            service_instance.yaw_characteristic.changed(packet)
            print(f"[송신] STM32 네이티브 방위각(Yaw) 앱으로 유출 중: {latest_stm32_yaw:.2f}°", end="\r")
                
        except Exception as e:
            print(f"\n[송신 익셉션 오류] {e}")
            
        await asyncio.sleep(YAW_TX_PERIOD_SEC)

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
    
    # 💡 두 개의 비동기 태스크(UART 수신 가동 + BLE 앱 송신 제어)를 동시에 병렬 실행(Concurrent)
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[시스템] 인터럽트 시그널 감지. 가이드 서버를 안전하게 종료합니다.")
        sys.exit(0)