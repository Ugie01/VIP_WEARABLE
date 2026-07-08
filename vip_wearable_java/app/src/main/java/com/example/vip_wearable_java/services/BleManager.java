package com.example.vip_wearable_java.services;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanSettings;
import java.util.ArrayList;
import java.util.List;

@SuppressLint("MissingPermission")
public class BleManager {
    private static final String TAG = "BLE_DEBUG";
    public static final UUID SERVICE_UUID = UUID.fromString("0000ffe0-0000-1000-8000-00805f9b34fb");
    public static final UUID CHAR_YAW_NOTIFY_UUID = UUID.fromString("0000ffe1-0000-1000-8000-00805f9b34fb");
    public static final UUID CHAR_ERROR_WRITE_UUID = UUID.fromString("0000ffe2-0000-1000-8000-00805f9b34fb");
    private static final UUID CLIENT_CHARACTERISTIC_CONFIG_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    private static volatile BleManager instance;
    private final BluetoothAdapter bluetoothAdapter;
    private BluetoothLeScanner bleScanner;
    private BluetoothGatt bluetoothGatt;
    private BluetoothGattCharacteristic writeCharacteristic;

    private BleStateCallback stateCallback;
    private BleDataCallback dataCallback;

    private ScheduledExecutorService txExecutor;
    private long txPeriodMs = 200;
    private boolean isGuidingRef = false;
    private float currentErrorRef = 0.0f;
    private boolean isUserExplicitDisconnect = false;
    private BluetoothDevice connectedDeviceRef = null;

    public interface BleStateCallback {
        void onConnectionStateChanged(int status);
        void onDeviceFound(BluetoothDevice device);
    }

    public interface BleDataCallback {
        void onYawReceived(float yaw);
    }

    public static BleManager getInstance() {
        if (instance == null) {
            synchronized (BleManager.class) {
                if (instance == null) {
                    instance = new BleManager();
                }
            }
        }
        return instance;
    }

    private BleManager() {
        this.bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
        if (bluetoothAdapter != null) {
            this.bleScanner = bluetoothAdapter.getBluetoothLeScanner();
        }
    }

    public void setCallbacks(BleStateCallback stateCallback, BleDataCallback dataCallback) {
        this.stateCallback = stateCallback;
        this.dataCallback = dataCallback;
    }

    public void setTxPeriod(long periodMs) {
        this.txPeriodMs = periodMs;
        if (bluetoothGatt != null && writeCharacteristic != null) {
            restartTxLoop();
        }
    }

    public void sendStatePacket(int state) {
        if (bluetoothGatt == null || writeCharacteristic == null) return;
        byte[] packet = new byte[2];
        packet[0] = (byte) 0x33;
        packet[1] = (byte) state;

        writeCharacteristic.setValue(packet);
        writeCharacteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        bluetoothGatt.writeCharacteristic(writeCharacteristic);
        Log.d(TAG, "상태 플래그 [0x33, 0x0" + state + "] 라즈베리파이 전송 완료");
    }

    public void updateGuideState(boolean isGuiding, float currentError) {
        if (isGuiding && !this.isGuidingRef) {
            sendStatePacket(2);
        }
        this.isGuidingRef = isGuiding;
        this.currentErrorRef = currentError;
    }

    public void startScan() {
        if (bleScanner == null) return;
        List<ScanFilter> filters = new ArrayList<>();
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build();
        bleScanner.startScan(filters, settings, scanCallback);
    }

    public void connectByMac(Context context, String macAddress) {
        if (bluetoothAdapter == null) return;
        try {
            BluetoothDevice device = bluetoothAdapter.getRemoteDevice(macAddress);
            connect(context, device);
        } catch (IllegalArgumentException e) {
            Log.e(TAG, "유효하지 않은 MAC 주소: " + e.getMessage());
        }
    }

    public void stopScan() {
        if (bleScanner == null) return;
        bleScanner.stopScan(scanCallback);
    }

    public void stopGuidanceOnly() {
        Log.d(TAG, "[시퀀스] 주행 안내가 취소/종료되었습니다. 대기 상태(0x01)로 복귀합니다.");

        // 방향값(0x22)을 쏘는 200ms 루프를 먼저 즉각 차단합니다.
        this.isGuidingRef = false;
        this.currentErrorRef = 0.0f;

        // 안드로이드 송신 버퍼가 비워질 시간을 100ms 준 뒤에 0x33을 안전하게 쏩니다.
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            sendStatePacket(1);
        }, 100);
    }

    public void forceBleDisconnect() {
        Log.d(TAG, "[시퀀스] 사용자가 수동으로 연결 해제를 요청했습니다.");
        this.isUserExplicitDisconnect = true;
        sendStatePacket(0);

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            this.connectedDeviceRef = null;
            stopTxLoop();
            this.isGuidingRef = false;

            if (bluetoothGatt != null) {
                bluetoothGatt.disconnect();
                bluetoothGatt.close();
                bluetoothGatt = null;
            }
            writeCharacteristic = null;

            if (stateCallback != null) {
                stateCallback.onConnectionStateChanged(BluetoothProfile.STATE_DISCONNECTED);
            }
        }, 100);
    }

    public void connect(Context context, BluetoothDevice device) {
        stopScan();
        this.isUserExplicitDisconnect = false;
        this.connectedDeviceRef = device;
        bluetoothGatt = device.connectGatt(context, false, gattCallback);
    }

    public void disconnect() {
        forceBleDisconnect();
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            if (stateCallback != null && result.getDevice() != null) {
                stateCallback.onDeviceFound(result.getDevice());
            }
        }
    };

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            if (stateCallback != null) {
                new Handler(Looper.getMainLooper()).post(() -> stateCallback.onConnectionStateChanged(newState));
            }

            if (newState == BluetoothProfile.STATE_CONNECTED) {
                Log.d(TAG, "BLE 물리적 연결 성공. 600ms 대기 후 MTU 확장을 요청합니다.");

                // 🌟 [핵심 1] 바로 서비스 탐색을 하지 않고, MTU(패킷 크기) 확장을 요청해 안드로이드 스택을 조율합니다.
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    if (bluetoothGatt != null) {
                        bluetoothGatt.requestMtu(256);
                    }
                }, 600);

            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                stopTxLoop();
                writeCharacteristic = null;

                if (!isUserExplicitDisconnect) {
                    Log.d(TAG, "⚠️ [경고] 의도치 않은 블루투스 단절 발생! 자동 재연결 시퀀스를 유지합니다.");
                    if (stateCallback != null) {
                        new Handler(Looper.getMainLooper()).post(() ->
                                stateCallback.onConnectionStateChanged(1)
                        );
                    }
                } else {
                    if (bluetoothGatt != null) {
                        bluetoothGatt.close();
                        bluetoothGatt = null;
                    }
                }
            }
        }

        // 🌟 [핵심 2] MTU 확장이 완료(또는 실패)된 후에야 비로소 서비스 탐색을 시작합니다.
        @Override
        public void onMtuChanged(BluetoothGatt gatt, int mtu, int status) {
            Log.d(TAG, "MTU 확장 협상 완료(mtu=" + mtu + "). 서비스 탐색을 시작합니다.");
            if (bluetoothGatt != null) {
                bluetoothGatt.discoverServices();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                BluetoothGattService service = gatt.getService(SERVICE_UUID);
                if (service != null) {
                    BluetoothGattCharacteristic readChar = service.getCharacteristic(CHAR_YAW_NOTIFY_UUID);
                    writeCharacteristic = service.getCharacteristic(CHAR_ERROR_WRITE_UUID);

                    if (readChar != null) {
                        gatt.setCharacteristicNotification(readChar, true);
                        android.bluetooth.BluetoothGattDescriptor descriptor = readChar.getDescriptor(CLIENT_CHARACTERISTIC_CONFIG_UUID);
                        if (descriptor != null) {
                            descriptor.setValue(android.bluetooth.BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                            gatt.writeDescriptor(descriptor);
                        }
                    }
                }
            }
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt gatt, android.bluetooth.BluetoothGattDescriptor descriptor, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                Log.d(TAG, "Notify 채널 활성화 핸드셰이크 성공. 안드로이드 통신 파라미터 완전 안정화를 위해 1.5초 대기합니다.");

                // 🌟 [핵심 3] 모든 세팅이 끝나고 연결 주기가 완전히 정착될 때까지 1.5초 뜸을 들인 후 첫 패킷 전송
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    sendStatePacket(1);
                    setTxPeriod(200);
                }, 1500);
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            if (CHAR_YAW_NOTIFY_UUID.equals(characteristic.getUuid())) {
                byte[] data = characteristic.getValue();
                if (data == null || data.length != 5 || data[0] != (byte) 0x11) return;

                java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(data, 1, 4);
                buffer.order(java.nio.ByteOrder.BIG_ENDIAN);
                float receivedYaw = buffer.getFloat();

                if (dataCallback != null) {
                    dataCallback.onYawReceived(receivedYaw);
                }
            }
        }
    };

    private synchronized void restartTxLoop() {
        stopTxLoop();
        txExecutor = Executors.newSingleThreadScheduledExecutor();
        txExecutor.scheduleAtFixedRate(this::sendGuidePacket, 0, txPeriodMs, TimeUnit.MILLISECONDS);
    }

    private synchronized void stopTxLoop() {
        if (txExecutor != null && !txExecutor.isShutdown()) {
            txExecutor.shutdown();
            txExecutor = null;
        }
    }

    private void sendGuidePacket() {
        if (bluetoothGatt == null || writeCharacteristic == null) return;
        if (!isGuidingRef) return;

        byte[] packet = new byte[5];
        packet[0] = (byte) 0x22;

        int bits = Float.floatToIntBits(currentErrorRef);
        packet[1] = (byte) (bits >> 24);
        packet[2] = (byte) (bits >> 16);
        packet[3] = (byte) (bits >> 8);
        packet[4] = (byte) (bits);

        writeCharacteristic.setValue(packet);
        writeCharacteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        bluetoothGatt.writeCharacteristic(writeCharacteristic);
    }
}