import asyncio  # 비동기 I/O 처리 루프 및 태스크 관리 목적
import struct  # C 구조체 형식 바이트 패킹 및 언패킹 목적
import sys  # 시스템 특정 파라미터 제어 및 프로세스 강제 종료 목적
import time  # 타임아웃 계산용 실시간 유닉스 타임스탬프 측정 목적
import subprocess  # 리눅스 커널 블루투스 제어 도구(btmgmt) 외부 프로세스 실행 목적
import serial  # UART 직렬 통신용 시리얼 포트 제어 목적
from bluez_peripheral.util import * # BlueZ D-Bus 통신 설정용 유틸리티 함수 로드
from bluez_peripheral.gatt.service import Service  # GATT 서비스 클래스 정의 및 상속 목적
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags  # GATT 속성 및 플래그 설정 목적

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"  # 안드로이드 앱 탐색용 하드코딩 GATT 서비스 고유 식별자
CHAR_YAW_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # 앱 대상 방위각 데이터 실시간 푸시(Notify) 매핑 UUID
CHAR_ERROR_WRITE_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"  # 앱 송신 오차 데이터 고속 수신(Write Without Response) 매핑 UUID

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
"""  # dbus-next 라이브러리 인터페이스 파싱 버그 방지용 수동 주입 XML 명세서

YAW_TX_PERIOD_SEC = 0.1  # 초당 10회(10Hz) 주기의 데이터 송신 주기 설정값
DISCONNECT_TIMEOUT_SEC = 2.0  # 네트워크 단절 판단 임계치 시간(2초)

UART_PORT = "/dev/ttyAMA0"  # 라즈베리파이 5 하드웨어 표준 UART 포트 경로 지정
BAUDRATE = 115200  # STM32 통신 규격 동기화용 보레이트 설정값

latest_stm32_yaw = 0.0  # 센서 수신 최신 방위각(Yaw) 데이터 전역 유지 변수
has_st_awakened = False  # 스마트폰 앱 최초 연결 및 유효 데이터 수신 활성화 플래그 변수
last_rx_packet_time = 0.0  # 하트비트 체크용 마지막 수신 패킷 타임스탬프 기록 변수

global_ser = None  # 시리얼 포트 객체 전역 공유 변수
detected_adapter_index = "0"  # 시스템 자동 감지 블루투스 어댑터 인덱스 저장 변수

def reset_hardware_to_sleep():
    global has_st_awakened, latest_stm32_yaw, global_ser  # 전역 변수 참조 선언
    if has_st_awakened:  # 가동 중 상태 조건 검사
        has_st_awakened = False  # 가동 상태 플래그 비활성화 전환
        print("\n==================================================")  # 시각적 구분선 출력
        print("[시스템 시퀀스] 연결 단절 조치 및 대기 모드 진입")  # 통신 유실 안내 로그 출력
        print("[하드웨어] ST 보드를 슬립 모드(0x00)로 리셋 조치합니다.")  # 대기 모드 복귀 공지 출력
        print("==================================================")  # 시각적 구분선 출력
        send_control_flag_to_stm32(0x00)  # STM32 보드 대상 슬립 명령 패킷 전송
        latest_stm32_yaw = 0.0  # 내부 방위각 데이터 초기화
        if global_ser and global_ser.is_open:  # 시리얼 포트 개방 여부 검사 조건문
            global_ser.reset_input_buffer()  # 잔여 버퍼 밀림 방지용 입력 버퍼 클리어

def send_control_flag_to_stm32(flag_value):
    global global_ser  # 전역 변수 참조 선언
    if global_ser and global_ser.is_open:  # 시리얼 포트 유효성 검사 조건문
        try:
            packet = bytearray([0xAA]) + struct.pack('!f', 0.0) + bytearray([flag_value])  # 제어 플래그 포함 6바이트 패킷 생성
            global_ser.write(packet)  # 시리얼 포트 데이터 쓰기 실행
            global_ser.flush()  # 물리 전송 즉시 완료 보장 목적의 버퍼 플러시
            status_text = "구동(Wake)" if flag_value == 0x01 else "대기/초기화(Sleep)"  # 터미널 출력용 문자열 분기 연산
            print(f"[하드웨어 제어] ST 보드로 {status_text} 명령 플래그({hex(flag_value)}) 전송 완료.")  # 제어 로그 출력
        except Exception as e:
            print(f"[하드웨어 제어 오류] ST 플래그 전파 실패: {e}")  # 전송 실패 예외 처리 블록

def send_angle_error_to_stm32(angle_error):
    global global_ser  # 전역 변수 참조 선언
    if global_ser and global_ser.is_open:  # 시리얼 포트 유효성 검사 조건문
        try:
            packet = bytearray([0xAA]) + struct.pack('!f', angle_error) + bytearray([0x01])  # 오차 데이터 포함 6바이트 패킷 생성
            global_ser.write(packet)  # 시리얼 포트 오차 패킷 전송 실행
        except Exception as e:
            print(f"[하드웨어 제어 오류] ST 오차 데이터 전파 실패: {e}")  # 전송 실패 예외 처리 블록

class TrackerGattService(Service):  # BlueZ GATT 서비스 규격 구현 클래스
    def __init__(self):
        super().__init__(SERVICE_UUID, True)  # 부모 생성자 호출 및 기본 서비스 속성 등록
        print("[시스템] GATT 서버 서비스 스펙트럼 인스턴스 초기화 완료.")  # 서비스 객체 생성 완료 로그 출력

    @characteristic(CHAR_YAW_NOTIFY_UUID, CharacteristicFlags.NOTIFY)  # Notify 플래그 속성 선언 데코레이터
    def yaw_characteristic(self, options):
        return bytearray([0x11, 0x00, 0x00, 0x00, 0x00])  # 최초 읽기 요청 대응 5바이트 기본 데이터 구조 반환

    @characteristic(CHAR_ERROR_WRITE_UUID, CharacteristicFlags.WRITE_WITHOUT_RESPONSE)  # Write 플래그 속성 선언 데코레이터
    def error_characteristic(self, options):
        pass  # 읽기 요청 예외 대응용 빈 메서드 정의

    @error_characteristic.setter  # 비동기식 세터(Setter) 메서드 지정 데코레이터
    def error_characteristic(self, value, options):
        global has_st_awakened, global_ser, last_rx_packet_time  # 전역 변수 참조 선언
        try:
            if len(value) == 5 and value[0] == 0x22:  # 5바이트 길이 및 헤더 식별자 검증 조건문
                angle_error = struct.unpack('!f', value[1:5])[0]  # 빅엔디안 float 데이터 디코딩 실행
                last_rx_packet_time = time.time()  # 최근 패킷 유입 타임스탬프 최신화

                if not has_st_awakened:  # 최초 유효 데이터 유입 시점 검사 조건문
                    has_st_awakened = True  # 시스템 활성화 상태 전환
                    print("\n==================================================")  # 시각적 구분선 출력
                    print("[BLE 이벤트] 안드로이드 앱 연동 성공! 나침반 및 통신 가동.")  # 연동 성공 안내 로그 출력
                    print("==================================================")  # 시각적 구분선 출력
                    if global_ser and global_ser.is_open:  # 시리얼 포트 개방 상태 점검 조건문
                        global_ser.reset_input_buffer()  # 수신 누적 데이터 정리 목적의 버퍼 초기화
                    send_control_flag_to_stm32(0x01)  # STM32 보드 대상 가동 명령 전송

                send_angle_error_to_stm32(angle_error)  # 실시간 오차 데이터 STM32 보드 즉시 다운스트림 전송

                if angle_error != 0.0:  # 경로 편차 오차 발생 검사 조건문
                    direction = "오른쪽" if angle_error > 0 else "왼쪽"  # 부호 기준 보정 방향 연산
                    print(f"[수신] 앱 경로 편차 오차: {angle_error:.1f}° -> {direction} 보정 확인          ", end="\n\r")  # 오차 실시간 출력
                else:
                    print("[상태] Tmap 안내 대기 중 | 실시간 나침반 스트리밍 가동 중", end="\r")  # 대기 상태 실시간 출력
            else:
                print(f"\n[경고] 앱 통신 규격 부적합 프로토콜 유입 무효화: {value.hex()}")  # 규격 미달 패킷 예외 로그 출력
        except Exception as e:
            print(f"\n[오류] 앱 패킷 디코딩 실패: {e}")  # 패킷 디코딩 예외 처리 블록

def force_kernel_advertising():
    print("[로그] 커널 레벨 BLE 광고 설정 및 강제 기동 중...")  # 커널 직접 명령 수행 로그 출력
    try:
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)  # 기존 광고 인스턴스 초기화 명령어 실행
        subprocess.run(["sudo", "btmgmt", "--index", "0", "le", "on"], check=True, capture_output=True)  # Low Energy 기능 활성화 명령어 실행
        subprocess.run(["sudo", "btmgmt", "--index", "0", "pairable", "off"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "connectable", "on"], capture_output=True)
        subprocess.run(["sudo", "btmgmt", "--index", "0", "power", "on"], check=True, capture_output=True)  # 블루투스 장치 전원 인가 명령어 실행
        
        subprocess.run([
            "sudo", "btmgmt", "--index", "0", "add-adv",
            "-u", "ffe0", 
            "-c",         
            "-n",         
            "1"           
        ], check=True, capture_output=True)  # UUID 포함 및 기기 이름 브로드캐스팅 활성화 광고 기동 명령어 실행
        
        subprocess.run(["sudo", "bluetoothctl", "system-alias", "VIP_Guide"], capture_output=True)  # 장치 스캔용 별칭 지정 명령어 실행
        print("✅ [성공] 커널 레벨 BLE 광고 송출 완벽 가동! (기기 이름: VIP_Guide)")  # 광고 가동 완료 로그 출력
    except Exception as e:
        print(f"❌ [실패] 커널 광고 제어 실패: {e}")  # 커널 제어 예외 처리 블록

async def read_stm32_uart_loop():
    global latest_stm32_yaw, global_ser, has_st_awakened  # 전역 변수 참조 선언
    print(f"[하드웨어] STM32 수신용 UART 채널 바인딩 가동 ({UART_PORT}, {BAUDRATE}bps)")  # 채널 개방 시작 안내 로그 출력
    
    try:
        global_ser = serial.Serial(UART_PORT, baudrate=BAUDRATE, timeout=0.1)  # 하드웨어 시얼 포트 오픈 및 객체 할당
    except Exception as e:
        print(f"[하드웨어 오류] UART 포트 개방 실패 (권한 누락 또는 장치 없음): {e}")  # 채널 오픈 오류 예외 로그 출력
        return

    while True:  # 무한 데이터 수신 청취 루프 블록
        try:
            if not has_st_awakened:  # 앱 미연결 대기 상태 조건문
                if global_ser.is_open and global_ser.in_waiting > 0:  # 개방 상태 및 데이터 잔존 여부 검사
                    global_ser.reset_input_buffer()  # 무효 패킷 적체 방지용 버퍼 초기화
                await asyncio.sleep(0.1)  # 루프 속도 제어용 비동기 대기 수행
                continue

            if global_ser.is_open and global_ser.in_waiting >= 5:  # 유효 수신 패킷 최소 바이트(5바이트) 충족 검사 조건문
                header = global_ser.read(1)  # 1바이트 헤더 영역 읽기 수행
                if header == b'\xaa':  # STM32 프로토콜 고유 헤더 확인 조건문
                    payload = global_ser.read(4)  # 4바이트 페이로드 영역 읽기 수행
                    parsed_yaw = struct.unpack('<f', payload)[0]  # 리틀엔디안 float 데이터 디코딩 실행
                    
                    if -180.0 <= parsed_yaw <= 180.0:  # 유효 방위각 수치 범위 필터링 조건문
                        latest_stm32_yaw = parsed_yaw  # 전역 최신 방위각 데이터 최신화 갱신
                        
        except Exception as e:
            print(f"\n[UART 통신 오류] 데이터 스트림 무효화: {e}")  # 스트림 해석 오류 예외 처리 블록
            
        await asyncio.sleep(0.01)  # 직렬 버퍼 과부하 방지용 미세 비동기 슬립 수행

async def send_yaw_loop(service_instance):
    print(f"[가이드] {int(YAW_TX_PERIOD_SEC * 1000)}ms 주기 네이티브 방위각 스트리밍 타이머 가동.")  # 주기 전송 시작 안내 로그 출력
    global latest_stm32_yaw, has_st_awakened  # 전역 변수 참조 선언
    
    while True:  # 무한 전송 루프 블록
        try:
            if not has_st_awakened:  # 연결 미활성화 상태 검사 조건문
                await asyncio.sleep(YAW_TX_PERIOD_SEC)  # CPU 자원 독점 방지용 대기 수행
                continue

            raw_packet = bytearray([0x11]) + struct.pack('!f', latest_stm32_yaw)  # 헤더 및 STM32 실수 방위각 포함 5바이트 송신 패킷 생성
            packet = bytes(raw_packet)  # bytes 타입 형변환
            
            service_instance.yaw_characteristic.changed(packet)  # BlueZ D-Bus 스택 대상 데이터 변경 이벤트 전달 및 앱 Notify 송신
            print(f"[송신] STM32 네이티브 방위각(Yaw) 앱 전송 중: {latest_stm32_yaw:.2f}°", end="\r")  # 터미널 실시간 전송 현황 덮어쓰기 출력
                
        except Exception as e:
            # [단절 감지 2] 송신 실패를 통한 물리적 네트워크 파괴 감지
            error_type = type(e).__name__
            print(f"\n[단절 원인 분석 - 예외 발생] 송신 중 치명적 오류. ({error_type}: {e})")
            if "DBusError" in error_type or "Broken" in str(e) or "Timeout" in str(e):
                 print(" -> OS 커널 레벨 통신 파이프 파괴. (물리적 거리 이탈, 강한 전파 간섭, 혹은 BLE 버퍼 오버플로우가 원인입니다.)")
            reset_hardware_to_sleep()  # 전송 실패 발생 시 시스템 대기 모드 복귀 함수 호출
            
        await asyncio.sleep(YAW_TX_PERIOD_SEC)  # 비동기 주기 타이머 제어권 반환 대기 수행

async def track_software_heartbeat_timeout():
    global has_st_awakened, last_rx_packet_time  # 전역 변수 참조 선언
    while True:  # 백그라운드 모니터링 무한 루프 블록
        try:
            if has_st_awakened and (time.time() - last_rx_packet_time > DISCONNECT_TIMEOUT_SEC):  # 타임아웃 초과 여부 검사 조건문
                # [단절 감지 3] 데이터 유입 타임아웃을 통한 논리적 연결 유실 감지
                print(f"\n[단절 원인 분석 - 논리적 타임아웃] {DISCONNECT_TIMEOUT_SEC}초간 앱으로부터 응답 없음.")
                print(" -> BLE 연결은 유지되어 있으나, 안드로이드 OS의 배터리 최적화로 인해 앱이 프리징되었거나 스레드가 정지되었습니다.")
                reset_hardware_to_sleep()  # 장치 상태 리셋 함수 호출
        except Exception:
            pass  # 모니터링 루프 예외 무시 처리
        await asyncio.sleep(0.5)  # 검사 주기 조율용 비동기 대기 수행

async def main():
    print("[로그] 1단계: D-Bus 메시지 버스 연결 시도 중...")  # D-Bus 연결 시도 단계 로그 출력
    try:
        bus = await get_message_bus()  # BlueZ 통신용 D-Bus 메시지 버스 객체 획득
        print("✅ [성공] D-Bus 메시지 버스 연결 완료")  # 연결 완료 로그 출력
    except Exception as e:
        print(f"❌ [실패] D-Bus 연결 오류: {e}")  # 연결 오류 발생 시 진입점 종료 처리
        return

    print("[로그] 2단계: /org/bluez/hci0 프록시 객체 고정 매핑 시도 중...")  # 어댑터 접근 단계 로그 출력
    try:
        proxy = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", ADAPTER_INSPECT)  # XML 명세 기반 프록시 객체 생성
        adapter = Adapter(proxy)  # GATT 관리용 BlueZ 어댑터 인스턴스 래핑
        print("✅ [성공] 블루투스 어댑터(hci0) 인터페이스 매핑 완료")  # 매핑 성공 로그 출력
    except Exception as e:
        print(f"❌ [실패] 어댑터 매핑 오류: {e}")  # 매핑 실패 발생 시 진입점 종료 처리
        return
        
    print("[로그] 3단계: GATT 서비스 스펙트럼 초기화 중...")  # 커스텀 GATT 서비스 인스턴스화 단계 로그 출력
    service = TrackerGattService()  # 커스텀 GATT 서비스 객체 생성 및 할당
    
    print("[로그] 4단계: GATT 서비스 서비스 등록 시도 중...")  # 서비스 등록 단계 로그 출력
    try:
        await service.register(bus, adapter=adapter, path="/org/bluez/app/service")  # 공식 GATT 트리 경로 상 서비스 등록 수행
        print("✅ [성공] GATT 데이터 통신 서비스 등록 완료")  # 등록 성공 로그 출력
    except Exception as e:
        print(f"❌ [실패] GATT 서비스 등록 에러: {e}")  # 등록 실패 발생 시 진입점 종료 처리
        return
    
    force_kernel_advertising()  # 커널 레이어 직접 명령 기반 광고 송출 함수 가동
    
    print("==================================================")  # 시각적 구분선 출력
    print("  라즈베리파이5 고속 BLE 가이드 서버")  # 시스템 로드 완료 타이틀 출력
    print("==================================================")  # 시각적 구분선 출력
    print("[대기] 스마트폰 어플리케이션으로부터 스캔 및 연결 바인딩을 기다립니다.")  # 접속 대기 상태 안내 공지 출력
    
    await asyncio.gather(
        send_yaw_loop(service),
        read_stm32_uart_loop(),  # 물리 하드웨어 계층 실시간 시리얼 스트리밍 루프 병렬 배치
        track_software_heartbeat_timeout()  # 앱 유실 감시용 정밀 하트비트 타임아웃 프로세스 병렬 배치
    )  # 통합 비동기 멀티태스크 동시 구동 개시

if __name__ == "__main__":  # 스크립트 직접 실행 여부 검사 조건문
    try:
        asyncio.run(main())  # 메인 비동기 이벤트 루프 실행
    except KeyboardInterrupt:  # Ctrl + C 수동 종료 시그널 감지 예외 블록
        print("\n[시스템] 인터럽트 시그널 감지. 가이드 서버를 안전하게 종료합니다.")  # 프로세스 종료 안내 로그 출력
        has_st_awakened = True  # 리셋 조건 만족용 상태 변경 조치
        reset_hardware_to_sleep()  # 하드웨어 변수 및 상태 원점 복귀 함수 호출
        if global_ser and global_ser.is_open:  # 개방된 시리얼 채널 잔존 유무 검사 조건문
            global_ser.close()  # 하드웨어 시리얼 포트 자원 명시적 반환 및 종료 폐쇄
        subprocess.run(["sudo", "btmgmt", "--index", "0", "clr-adv"], capture_output=True)  # 잔존 커널 광고 인스턴스 강제 삭제
        sys.exit(0)  # 정상 종료 코드 반환 및 프로세스 최종 종료 명시