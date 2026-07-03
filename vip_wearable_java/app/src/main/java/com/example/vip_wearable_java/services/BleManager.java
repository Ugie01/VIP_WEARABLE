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
import android.os.ParcelUuid;
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

    public void updateGuideState(boolean isGuiding, float currentError) {
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
        Log.d(TAG, "[시퀀스] 주행 안내가 종료되었습니다. BLE 나침반 스트리밍은 유지합니다.");
        stopTxLoop();
        this.isGuidingRef = false;
        this.currentErrorRef = 0.0f;
    }

    public void forceBleDisconnect() {
        Log.d(TAG, "[시퀀스] 사용자가 수동으로 BLE 연결 해제를 요청했습니다. 재연결을 차단합니다.");
        this.isUserExplicitDisconnect = true;
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
            new Handler(Looper.getMainLooper()).post(() ->
                    stateCallback.onConnectionStateChanged(BluetoothProfile.STATE_DISCONNECTED)
            );
        }
    }
    public void connect(Context context, BluetoothDevice device) {
        stopScan();
        this.isUserExplicitDisconnect = false;
        this.connectedDeviceRef = device;
        bluetoothGatt = device.connectGatt(context, true, gattCallback);
    }

    public void disconnect() {
        Log.d(TAG, "[시퀀스 1단계] 스마트폰 단에서 수동 연결 해제 프로세스 진입.");
        updateGuideState(false, 0.0f);
        sendGuidePacket();
        stopTxLoop();

        if (bluetoothGatt != null) {
            bluetoothGatt.disconnect();
            bluetoothGatt.close();
            bluetoothGatt = null;
        }

        writeCharacteristic = null;
        if (stateCallback != null) {
            new Handler(Looper.getMainLooper()).post(() ->
                    stateCallback.onConnectionStateChanged(BluetoothProfile.STATE_DISCONNECTED)
            );
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
                gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH);
                gatt.discoverServices();
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

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                BluetoothGattService service = gatt.getService(SERVICE_UUID);
                if (service != null) {
                    BluetoothGattCharacteristic readChar = service.getCharacteristic(CHAR_YAW_NOTIFY_UUID);
                    writeCharacteristic = service.getCharacteristic(CHAR_ERROR_WRITE_UUID);
                    gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH);
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
                Log.d("BLE_DEBUG", "Notify 채널 활성화 핸드셰이크 최종 성공. 이제 역송신을 시작합니다.");
            }
            setTxPeriod(200);
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            if (CHAR_YAW_NOTIFY_UUID.equals(characteristic.getUuid())) {
                byte[] data = characteristic.getValue();

                if (data == null) {
                    Log.d("BLE_DEBUG", " [수신 에러] 로우 데이터 패킷이 null입니다.");
                    return;
                }

                StringBuilder sb = new StringBuilder();
                for (byte b : data) {
                    sb.append(String.format("%02X ", b));
                }
                Log.d("BLE_DEBUG", " [패킷 수신] 길이: " + data.length + " bytes | 데이터(HEX): [ " + sb.toString().trim() + " ]");

                if (data.length != 5) {
                    Log.d("BLE_DEBUG", " [필터 탈락] 패킷 규격이 5바이트가 아닙니다. (현재: " + data.length + ")");
                    return;
                }
                if (data[0] != (byte) 0x11) {
                    Log.d("BLE_DEBUG", "❌ [필터 탈락] 헤더 바이트가 0x11이 아닙니다. (현재 헤더: 0x" + String.format("%02X", data[0]) + ")");
                    return;
                }

                java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(data, 1, 4);
                buffer.order(java.nio.ByteOrder.BIG_ENDIAN);
                float receivedYaw = buffer.getFloat();

                Log.d("BLE_DEBUG", "✅ [파싱 성공] 최종 변환된 Yaw 각도값: " + receivedYaw + "°");

                if (dataCallback != null) {
                    dataCallback.onYawReceived(receivedYaw);
                } else {
                    Log.d("BLE_DEBUG", "⚠️ [콜백 인터셉트] dataCallback 인터페이스가 null 상태라 ViewModel로 값을 넘기지 못했습니다.");
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

        byte[] packet = new byte[5];
        packet[0] = (byte) 0x22; // 헤더 지정

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