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

@SuppressLint("MissingPermission")
public class BleManager {
    private static final String TAG = "BLE_DEBUG";

    // 💡 라즈베리파이 BLE GATT 서비스 및 캐릭터리스틱 UUID 설정
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
    private long txPeriodMs = 300; // 💡 통신 주기 하이퍼파라미터 (기본값 300ms)
    private boolean isGuidingRef = false;
    private float currentErrorRef = 0.0f;

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

    public void updateGuideState(boolean isGuiding, float currentError) {
        this.isGuidingRef = isGuiding;
        this.currentErrorRef = currentError;
    }

    public void startScan() {
        if (bleScanner == null) return;
        bleScanner.startScan(scanCallback);
    }

    public void stopScan() {
        if (bleScanner == null) return;
        bleScanner.stopScan(scanCallback);
    }

    public void connect(Context context, BluetoothDevice device) {
        stopScan();
        bluetoothGatt = device.connectGatt(context, false, gattCallback);
    }

    public void disconnect() {
        stopTxLoop();
        if (bluetoothGatt != null) {
            bluetoothGatt.disconnect();
            bluetoothGatt.close();
            bluetoothGatt = null;
        }
        if (stateCallback != null) {
            stateCallback.onConnectionStateChanged(BluetoothProfile.STATE_DISCONNECTED);
        }
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
                gatt.discoverServices();
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                stopTxLoop();
                writeCharacteristic = null;
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                BluetoothGattService service = gatt.getService(SERVICE_UUID);
                if (service != null) {
                    // 수신 및 송신 Characteristic 획득
                    BluetoothGattCharacteristic readChar = service.getCharacteristic(CHAR_YAW_NOTIFY_UUID);
                    writeCharacteristic = service.getCharacteristic(CHAR_ERROR_WRITE_UUID);

                    // 라즈베리파이의 Notify 수신 활성화 설정 적용
                    if (readChar != null) {
                        gatt.setCharacteristicNotification(readChar, true);
                        android.bluetooth.BluetoothGattDescriptor descriptor = readChar.getDescriptor(CLIENT_CHARACTERISTIC_CONFIG_UUID);
                        if (descriptor != null) {
                            descriptor.setValue(android.bluetooth.BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                            gatt.writeDescriptor(descriptor);
                        }
                    }
                    // 하이퍼파라미터 주기에 의거한 역송신 타이머 시작
                    restartTxLoop();
                }
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            if (CHAR_YAW_NOTIFY_UUID.equals(characteristic.getUuid())) {
                byte[] data = characteristic.getValue();
                // 프로토콜 무결성 검증: 5바이트 고정 크기 및 헤더 0x11 체킹
                if (data != null && data.length == 5 && data[0] == (byte) 0x11) {
                    int bits = ((data[1] & 0xFF) << 24) |
                            ((data[2] & 0xFF) << 16) |
                            ((data[3] & 0xFF) << 8)  |
                            ((data[4] & 0xFF));
                    float receivedYaw = Float.intBitsToFloat(bits);

                    if (dataCallback != null) {
                        dataCallback.onYawReceived(receivedYaw);
                    }
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
        if (bluetoothGatt == null || writeCharacteristic == null || !isGuidingRef) return;

        // 5바이트 구조 빌드: [0x22] + [Float 4Bytes Error]
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