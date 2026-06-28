import asyncio
import struct
import random
from bluez_peripheral.util import *
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_YAW_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_ERROR_WRITE_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

class TrackerGattService(Service):
    def __init__(self):
        super().__init__(SERVICE_UUID, True)
        print("[시스템] GATT 서비스가 초기화되었습니다.")

    # 변경 코드: gatt_property.NOTIFY -> CharacteristicFlags.NOTIFY
    @characteristic(CHAR_YAW_NOTIFY_UUID, CharacteristicFlags.NOTIFY)
    def yaw_characteristic(self, options):
        return bytearray([0x11, 0x00, 0x00, 0x00, 0x00])

    # 변경 코드: gatt_property.WRITE_WITHOUT_RESPONSE -> CharacteristicFlags.WRITE_WITHOUT_RESPONSE
    @characteristic(CHAR_ERROR_WRITE_UUID, CharacteristicFlags.WRITE_WITHOUT_RESPONSE)
    def error_characteristic(self, options):
        pass

    @error_characteristic.setter
    def error_characteristic(self, options, value):
        try:
            if len(value) == 5 and value[0] == 0x22:
                angle_error = struct.unpack('!f', value[1:5])[0]
                if angle_error == 0.0:
                    print(f"\n[수신] 회전 오차: {angle_error:.1f}° -> 경로 중심 주행 중")
                else:
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"
                    print(f"\n[수신] 회전 오차: {angle_error:.1f}° -> {direction} 보정 명령")
            else:
                print(f"\n[경고] 프로토콜 포맷 불일치: {value.hex()}")
        except Exception as e:
            print(f"\n[오류] 패킷 파싱 거부: {e}")

async def send_yaw_loop(service_instance):
    print("[가이드] 300ms 데이터 스트리밍 타이머 구동 완료.")
    while True:
        try:
            mock_yaw = random.uniform(-180.0, 180.0)
            packet = bytearray([0x11]) + struct.pack('!f', mock_yaw)
            
            # 피드백: 수정된 Notify 호출 방식
            # 데코레이터 처리된 함수 객체의 changed 메서드를 호출하고 서비스 인스턴스를 인자로 전달
            TrackerGattService.yaw_characteristic.changed(service_instance, packet)
            
            print(f"[송신] 실시간 방위각(Yaw) 송출 중: {mock_yaw:.2f}°", end="\r")
        except Exception as e:
            print(f"\n[송신 오류] {e}")
        await asyncio.sleep(0.3)

async def main():
    # Ubuntu 환경 대응을 위해 시스템 버스로 명시적 지정 가능
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
    print("가상환경 세션 링크 바인딩 완료. 스캔을 대기합니다.")
    
    await send_yaw_loop(service)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[시스템] BLE 가이드 서버가 종료되었습니다.")