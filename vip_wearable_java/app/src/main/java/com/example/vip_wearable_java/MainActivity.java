package com.example.vip_wearable_java;

import android.Manifest;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothProfile;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.lifecycle.ViewModelProvider;
import com.example.vip_wearable_java.models.RouteSegment;
import com.example.vip_wearable_java.services.AudioService;
import com.example.vip_wearable_java.services.BleManager;
import com.example.vip_wearable_java.services.TmapService;
import com.example.vip_wearable_java.viewmodels.MapViewModel;
import com.skt.tmap.TMapView;
import com.skt.tmap.TMapPoint;
import com.skt.tmap.overlay.TMapPolyLine;
import com.example.vip_wearable_java.BuildConfig;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class MainActivity extends AppCompatActivity implements LocationListener, TMapView.OnMapReadyListener {

    private static final String TAG = "TMAP_DEBUG";

    private MapViewModel viewModel;
    private TMapView tMapView;
    private EditText searchController;
    private TextView tvYawStatus, tvNavigationMsg;
    private LocationManager locationManager;
    private ImageButton btnCancel;

    // 🔥 하드웨어 가속 컴포넌트 마커 정의
    private ImageView ivCustomUserMarker;

    private boolean isMapReady = false;
    private boolean isInitialLocationSet = false;
    private boolean isGuiding = false;

    private final ArrayList<BluetoothDevice> scannedBleDevices = new ArrayList<>();
    private ArrayAdapter<String> bleDeviceListAdapter;
    private ImageButton btnBleDisconnect;

    // 꼬임 방지 연산용 글로벌 상태 변수
    private float mLatestCalculatedAngle = 0f;
    private boolean mIsFirstAngleSync = true;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // ⚠️ [튕김 예방 핵심 1단계] setContentView 직후에 이미지 뷰 레이어 주입 완료
        ivCustomUserMarker = findViewById(R.id.iv_custom_user_marker);

        // ⚠️ [튕김 예방 핵심 2단계] 넣어주신 arrow.png 이미지를 이미지 뷰에 다이렉트 바인딩
        if (ivCustomUserMarker != null) {
            ivCustomUserMarker.setImageResource(R.drawable.arrow);
        }

        viewModel = new ViewModelProvider(this).get(MapViewModel.class);

        List<String> permissionList = new ArrayList<>();
        permissionList.add(Manifest.permission.ACCESS_FINE_LOCATION);
        permissionList.add(Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissionList.add(Manifest.permission.BLUETOOTH_SCAN);
            permissionList.add(Manifest.permission.BLUETOOTH_CONNECT);
        }
        ActivityCompat.requestPermissions(this, permissionList.toArray(new String[0]), 1000);

        LinearLayout mapContainer = findViewById(R.id.map_container);
        searchController = findViewById(R.id.search_controller);
        tvYawStatus = findViewById(R.id.tv_yaw_status);
        tvNavigationMsg = findViewById(R.id.tv_navigation_msg);
        ImageButton btnMic = findViewById(R.id.btn_mic);
        ImageButton btnSearch = findViewById(R.id.btn_search);
        btnCancel = findViewById(R.id.btn_cancel);
        ImageButton btnSettings = findViewById(R.id.btn_settings);
        btnBleDisconnect = findViewById(R.id.btn_ble_disconnect);
        ImageButton btnBleScan = findViewById(R.id.btn_ble_scan);

        if (btnBleScan != null) {
            btnBleScan.setOnClickListener(v -> showBleScanDialog());
        }

        tMapView = new TMapView(this);
        tMapView.setSKTMapApiKey(BuildConfig.TMAP_API_KEY);
        tMapView.setOnMapReadyListener(this);
        mapContainer.addView(tMapView);

        locationManager = (LocationManager) getSystemService(LOCATION_SERVICE);
        try {
            locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, this);
            locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1000, 0, this);
        } catch (SecurityException e) {
            Log.e(TAG, "위치 권한 에러: " + e.getMessage());
        }

        BleManager.getInstance().setCallbacks(new BleManager.BleStateCallback() {
            @Override
            public void onConnectionStateChanged(int newState) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    viewModel.bleConnectionState.postValue(2);
                    Toast.makeText(MainActivity.this, "라즈베리파이 연결 성공", Toast.LENGTH_SHORT).show();
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    viewModel.bleConnectionState.postValue(0);
                    Toast.makeText(MainActivity.this, "라즈베리파이 연결 해제", Toast.LENGTH_SHORT).show();
                }
            }

            @android.annotation.SuppressLint("MissingPermission")
            @Override
            public void onDeviceFound(BluetoothDevice device) {
                runOnUiThread(() -> {
                    if (!scannedBleDevices.contains(device) && device.getName() != null) {
                        scannedBleDevices.add(device);
                        bleDeviceListAdapter.add(device.getName() + "\n(" + device.getAddress() + ")");
                        bleDeviceListAdapter.notifyDataSetChanged();
                    }
                });
            }
        }, yaw -> {
            viewModel.updateYawFromBle(yaw);
        });

        viewModel.bleConnectionState.observe(this, state -> {
            if (state == 2) {
                tvYawStatus.setBackgroundColor(Color.parseColor("#4CAF50"));
                tvYawStatus.setTextColor(Color.WHITE);
                tvYawStatus.setText("기기 BLE 연결됨");
                if(btnBleScan != null) btnBleScan.setVisibility(View.GONE);
                if(btnBleDisconnect != null) btnBleDisconnect.setVisibility(View.VISIBLE);
            } else if (state == 1) {
                tvYawStatus.setBackgroundColor(Color.parseColor("#FFC107"));
                tvYawStatus.setTextColor(Color.BLACK);
                tvYawStatus.setText("기기 연결 중...");
            } else {
                tvYawStatus.setBackgroundColor(Color.parseColor("#F44336"));
                tvYawStatus.setTextColor(Color.WHITE);
                tvYawStatus.setText("기기 BLE 연결 안됨 (터치하여 스캔)");
                if(btnBleScan != null) btnBleScan.setVisibility(View.VISIBLE);
                if(btnBleDisconnect != null) btnBleDisconnect.setVisibility(View.GONE);
            }
        });

        tvYawStatus.setOnClickListener(v -> showBleScanDialog());

        // 💡 [실시간 회전 최적화 파이프라인]
        viewModel.currentYaw.observe(this, yaw -> {
            if (viewModel.bleConnectionState.getValue() != null && viewModel.bleConnectionState.getValue() == 2) {
                tvYawStatus.setText("기기 연결됨 | 방위각: " + String.format("%.1f", yaw) + "°");
            }

            if (isMapReady && ivCustomUserMarker != null) {
                float currentYawValue = yaw.floatValue();

                // [-180도 ↔ 180도 구간 교차 시 마커 역회전 방지 보정 알고리즘]
                if (mIsFirstAngleSync) {
                    mLatestCalculatedAngle = currentYawValue;
                    mIsFirstAngleSync = false;
                } else {
                    float angleDiff = currentYawValue - mLatestCalculatedAngle;

                    while (angleDiff < -180.0f) angleDiff += 360.0f;
                    while (angleDiff > 180.0f)  angleDiff -= 360.0f;

                    mLatestCalculatedAngle += angleDiff;

                    while (mLatestCalculatedAngle < -180.0f) mLatestCalculatedAngle += 360.0f;
                    while (mLatestCalculatedAngle > 180.0f)  mLatestCalculatedAngle -= 360.0f;
                }

                // 🚀 안드로이드 OS 하드웨어 가속 회전 명령어 적용 (깜빡임 0%)
                if (ivCustomUserMarker.getVisibility() == View.GONE) {
                    ivCustomUserMarker.setVisibility(View.VISIBLE);
                }
                ivCustomUserMarker.setRotation(mLatestCalculatedAngle);

                // 실시간 회전 발생 시 지도 동기화 유도
                tMapView.setCenterPoint(viewModel.curLat, viewModel.curLng);
            }
            if (isGuiding) {
                drawGuideLineToTarget();
            }
        });

        viewModel.navigationMessage.observe(this, msg -> tvNavigationMsg.setText(msg));

        searchController.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                performSearchAction();
                return true;
            }
            return false;
        });

        btnSearch.setOnClickListener(v -> performSearchAction());

        btnCancel.setOnClickListener(v -> {
            new AlertDialog.Builder(MainActivity.this)
                    .setTitle("경로 안내 취소")
                    .setMessage("정말로 진행 중인 안전 경로 안내를 종료하시겠습니까?\n(방위각 나침반 기능은 계속 유지됩니다.)")
                    .setPositiveButton("안내 종료", (dialog, which) -> {
                        isGuiding = false;
                        viewModel.setGuidingState(false);
                        BleManager.getInstance().stopGuidanceOnly();
                        viewModel.cancelRouteGuidance();
                        if (isMapReady) {
                            tMapView.removeAllTMapPolyLine();
                        }
                        searchController.setText("");
                        btnCancel.setVisibility(View.GONE);
                    })
                    .setNegativeButton("계속 주행", null)
                    .show();
        });

        btnBleDisconnect.setOnClickListener(v -> {
            new AlertDialog.Builder(MainActivity.this)
                    .setTitle("기기 연결 해제")
                    .setMessage("라즈베리파이 가이드 기기와의 블루투스 연결을 완전히 끊으시겠습니까?\n해제 시 웨어러블 장치들이 초기화(대기동작)됩니다.")
                    .setPositiveButton("연결 끊기", (dialog, which) -> {
                        BleManager.getInstance().forceBleDisconnect();
                    })
                    .setNegativeButton("연결 유지", null)
                    .show();
        });

        btnMic.setOnClickListener(v -> {
            viewModel.getAudioService().startListening(new AudioService.SpeechCallback() {
                @Override
                public void onResult(String text) {
                    searchController.setText(text);
                    showSearchConfirmationDialog(text);
                }
                @Override
                public void onStatusChange(boolean isListening) {}
            });
        });

        btnSettings.setOnClickListener(v -> {
            Intent intent = new Intent(MainActivity.this, AudioSettingsActivity.class);
            startActivity(intent);
        });
    }

    private void onDestinationArrived() {
        Toast.makeText(this, "목적지에 도착했습니다. 가이드를 안전 종료합니다.", Toast.LENGTH_LONG).show();
        isGuiding = false;
        viewModel.setGuidingState(false);
        BleManager.getInstance().stopGuidanceOnly();
        if (isMapReady) tMapView.removeAllTMapPolyLine();
        btnCancel.setVisibility(View.GONE);
    }

    private void showBleScanDialog() {
        scannedBleDevices.clear();
        bleDeviceListAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1);

        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle("연결할 라즈베리파이 선택");
        builder.setAdapter(bleDeviceListAdapter, (dialog, which) -> {
            BleManager.getInstance().stopScan();
            BluetoothDevice selectedDevice = scannedBleDevices.get(which);
            viewModel.bleConnectionState.setValue(1);
            BleManager.getInstance().connect(MainActivity.this, selectedDevice);
        });

        builder.setNegativeButton("스캔 중지", (dialog, which) -> BleManager.getInstance().stopScan());
        builder.setOnDismissListener(dialog -> BleManager.getInstance().stopScan());
        builder.show();

        BleManager.getInstance().startScan();
    }

    @Override
    public void onMapReady() {
        isMapReady = true;
        tMapView.setZoomLevel(18);
        forceMapCenterToCurrentLocation();
    }

    private void forceMapCenterToCurrentLocation() {
        if (!isMapReady || isInitialLocationSet) return;
        try {
            Location lastKnown = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (lastKnown == null) {
                lastKnown = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            }
            if (lastKnown != null) {
                tMapView.setCenterPoint(lastKnown.getLatitude(), lastKnown.getLongitude());
                viewModel.updateLocation(lastKnown.getLatitude(), lastKnown.getLongitude());

                if (ivCustomUserMarker != null && ivCustomUserMarker.getVisibility() == View.GONE) {
                    ivCustomUserMarker.setVisibility(View.VISIBLE);
                }
                isInitialLocationSet = true;
            }
        } catch (SecurityException e) {
            Log.e(TAG, "보안 예외: " + e.getMessage());
        }
    }

    private void drawGuideLineToTarget() {
        if (!isMapReady || tMapView == null) return;

        Map<String, Double> target = viewModel.getTargetLocation();
        if (target == null) return;

        ArrayList<TMapPoint> guidePoints = new ArrayList<>();
        guidePoints.add(new TMapPoint(viewModel.curLat, viewModel.curLng));
        guidePoints.add(new TMapPoint(target.get("lat"), target.get("lng")));

        TMapPolyLine guideLine = new TMapPolyLine("guide_line", guidePoints);
        guideLine.setLineColor(Color.parseColor("#00FFFF"));
        guideLine.setLineWidth(12);

        tMapView.addTMapPolyLine(guideLine);
    }

    private void performSearchAction() {
        String text = searchController.getText().toString().trim();
        if (!text.isEmpty()) {
            showSearchConfirmationDialog(text);
        }
    }

    private void showSearchConfirmationDialog(String keyword) {
        viewModel.verifyDestination(keyword, new TmapService.TmapCallback<Map<String, Object>>() {
            @Override
            public void onSuccess(Map<String, Object> result) {
                runOnUiThread(() -> {
                    new AlertDialog.Builder(MainActivity.this)
                            .setTitle("목적지 재확인")
                            .setMessage("'" + result.get("name") + "' 목적지가 맞습니까?\n맞으시면 아래 시작 버튼을 눌러주세요.")
                            .setPositiveButton("안내 시작", (dialog, which) -> {
                                viewModel.startConfirmedGuidance(new TmapService.TmapCallback<List<RouteSegment>>() {
                                    @Override
                                    public void onSuccess(List<RouteSegment> resultSegments) {
                                        viewModel.setRouteSegments(resultSegments);
                                        runOnUiThread(() -> {
                                            isGuiding = true;
                                            viewModel.setGuidingState(true);
                                            BleManager.getInstance().updateGuideState(true, 0.0f);
                                            drawRouteOnNativeMap(resultSegments);
                                            btnCancel.setVisibility(View.VISIBLE);
                                        });
                                    }
                                    @Override
                                    public void onFailure(Exception e) {
                                        Log.e(TAG, "경로 탐색 실패: " + e.getMessage());
                                    }
                                });
                            })
                            .setNegativeButton("다시 입력", null)
                            .show();
                });
            }
            @Override
            public void onFailure(Exception e) {
                Log.e(TAG, "POI 검색 실패: " + e.getMessage());
            }
        });
    }

    private void drawRouteOnNativeMap(List<RouteSegment> segments) {
        if (tMapView == null || !isMapReady) return;

        tMapView.removeAllTMapPolyLine();
        int lineCounter = 0;
        for (RouteSegment segment : segments) {
            ArrayList<TMapPoint> pointList = new ArrayList<>();
            for (Map<String, Double> coord : segment.getCoords()) {
                pointList.add(new TMapPoint(coord.get("lat"), coord.get("lng")));
            }

            String uniqueLineId = "line" + lineCounter;
            TMapPolyLine polyline = new TMapPolyLine(uniqueLineId, pointList);
            polyline.setLineColor(Color.parseColor(segment.getColor()));
            polyline.setLineWidth(12);

            tMapView.addTMapPolyLine(polyline);
            lineCounter++;
        }
        tMapView.invalidate();
    }

    @Override
    public void onLocationChanged(@NonNull Location location) {
        double lat = location.getLatitude();
        double lng = location.getLongitude();

        viewModel.updateLocation(lat, lng);
        if (!isMapReady || tMapView == null) return;

        // GPS 연동 위치 동기화
        tMapView.setCenterPoint(lat, lng);

        if (ivCustomUserMarker != null && ivCustomUserMarker.getVisibility() == View.GONE) {
            ivCustomUserMarker.setVisibility(View.VISIBLE);
        }

        if (!isInitialLocationSet) {
            isInitialLocationSet = true;
        }

        if (isGuiding) {
            drawGuideLineToTarget();
        }

        tMapView.invalidate();
    }
}