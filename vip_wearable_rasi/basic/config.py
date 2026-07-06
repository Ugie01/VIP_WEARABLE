
# basic/config.py
import struct
import cv2
import onnxruntime as ort

# 1. 라즈베리파이 5의 4개 코어를 모두 쓰도록 멀티스레딩 및 그래프 최적화 설정
options = ort.SessionOptions()
options.intra_op_num_threads = 4  # 라즈베리파이 5 CPU 코어 개수에 맞춤
options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

TIMER_INTERVAL = 1


VIDEO_SHM_NAME = "assist_video_shm"
WIDTH = 320
HEIGHT = 256
CHANNELS = 3
FRAME_SIZE = WIDTH * HEIGHT * CHANNELS

CAMERA_BACKEND = cv2.CAP_V4L2    
CAMERA_BUFFER_SIZE = 1  

PACKET_FORMAT = "!BfBB"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

PIPE_PATH = "/tmp/assist_event_pipe"
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 9999
SHOW_DISPLAY = True

# --- BLE 정적 상수 명세 ---
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