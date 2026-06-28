package com.example.vip_wearable_java.viewmodels;

import android.app.Application;
import androidx.annotation.NonNull;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.MutableLiveData;
import com.example.vip_wearable_java.models.RouteSegment;
import com.example.vip_wearable_java.services.AudioService;
import com.example.vip_wearable_java.services.BleManager;
import com.example.vip_wearable_java.services.TmapService;
import com.example.vip_wearable_java.BuildConfig;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

// 💡 SensorEventListener 상속 구조 제거 (BLE 외부 처리 전환)
public class MapViewModel extends AndroidViewModel {

    public MutableLiveData<Boolean> isLoading = new MutableLiveData<>(true);
    public MutableLiveData<Boolean> isListening = new MutableLiveData<>(false);
    public MutableLiveData<Double> currentYaw = new MutableLiveData<>(0.0);
    public MutableLiveData<Double> angleError = new MutableLiveData<>(0.0);
    public MutableLiveData<String> navigationMessage = new MutableLiveData<>("안내를 시작하려면 목적지를 입력하세요.");
    public MutableLiveData<Integer> bleConnectionState = new MutableLiveData<>(0); // 💡 0:미연결, 1:연결중, 2:연결됨

    private final TmapService tmapService;
    private final AudioService audioService;

    public List<RouteSegment> fullRouteSegments = new ArrayList<>();
    public Map<String, Object> tempPoiData;

    private int currentSegmentIndex = 0;
    private int currentCoordIndex = 0;

    public double curLat = 37.555142; //
    public double curLng = 126.970448; //

    private Map<String, Double> currentTargetCoord = null;
    private boolean isGuidingFlag = false;

    public MapViewModel(@NonNull Application application) {
        super(application);
        tmapService = new TmapService(BuildConfig.TMAP_API_KEY);
        audioService = new AudioService(application.getApplicationContext());

        // 💡 기존 하드웨어 센서 초기화 및 센서 매니저 바인딩 전면 소거
        isLoading.setValue(false);
    }

    public AudioService getAudioService() { return audioService; }

    public void setRouteSegments(List<RouteSegment> segments) {
        this.fullRouteSegments = segments;
        this.currentSegmentIndex = 0;
        this.currentCoordIndex = 0;
    }

    public void setGuidingState(boolean isGuiding) {
        this.isGuidingFlag = isGuiding;
        updateBleManagerTxContext();
    }

    // 💡 라즈베리파이 가상 Yaw 데이터를 직접 ViewModel 라이브데이터 인젝션 채널 구축
    public void updateYawFromBle(float rawYaw) {
        // 요구사항 규격: -180~180 입력 규격을 지도의 0~360 매핑용 도메인 값으로 안전 정규화 변환
        double normalizedYaw = (rawYaw + 360.0) % 360.0;
        currentYaw.postValue(normalizedYaw);
        if (!fullRouteSegments.isEmpty()) {
            calculateDirectionGuide();
        } else {
            updateBleManagerTxContext();
        }
    }

    private void updateBleManagerTxContext() {
        Double err = angleError.getValue();
        float currentErr = (err != null) ? err.floatValue() : 0.0f;
        BleManager.getInstance().updateGuideState(isGuidingFlag, currentErr);
    }

    public void verifyDestination(String keyword, TmapService.TmapCallback<Map<String, Object>> viewCallback) {
        if (keyword.isEmpty()) return;
        tmapService.searchPoi(keyword, new TmapService.TmapCallback<Map<String, Object>>() {
            @Override
            public void onSuccess(Map<String, Object> result) {
                tempPoiData = result;
                audioService.speak(result.get("name") + "이 맞습니까? 맞으시면 안내 시작을 눌러주세요.");
                viewCallback.onSuccess(result);
            }
            @Override
            public void onFailure(Exception e) {
                audioService.speak("목적지를 찾지 못했습니다. 다시 말씀해 주세요.");
                viewCallback.onFailure(e);
            }
        });
    }

    public void startConfirmedGuidance(TmapService.TmapCallback<List<RouteSegment>> viewCallback) {
        if (tempPoiData == null) return;
        double destLat = (double) tempPoiData.get("lat");
        double destLng = (double) tempPoiData.get("lng");
        String destName = (String) tempPoiData.get("name");

        audioService.speak(destName + " 까지 보도 안전 안내를 시작합니다.");
        tmapService.fetchPedestrianRoute(curLat, curLng, destLat, destLng, destName, new TmapService.TmapCallback<List<RouteSegment>>() {
            @Override
            public void onSuccess(List<RouteSegment> result) {
                setRouteSegments(result);
                calculateDirectionGuide();
                viewCallback.onSuccess(result);
            }
            @Override
            public void onFailure(Exception e) { viewCallback.onFailure(e); }
        });
    }

    public void cancelRouteGuidance() {
        fullRouteSegments.clear();
        tempPoiData = null;
        currentSegmentIndex = 0;
        currentCoordIndex = 0;
        setGuidingState(false);
        angleError.postValue(0.0);
        navigationMessage.postValue("안내를 시작하려면 목적지를 입력하세요.");
        audioService.speak("경로 안내를 종료합니다.");
    }

    public void updateLocation(double lat, double lng) {
        this.curLat = lat;
        this.curLng = lng;
        if (!fullRouteSegments.isEmpty()) {
            calculateDirectionGuide();
        }
    }

    public Map<String, Double> getTargetLocation() {
        return currentTargetCoord;
    }

    public void calculateDirectionGuide() {
        if (fullRouteSegments.isEmpty()) return;

        Map<String, Double> targetCoord = getValidTargetCoordinate();
        this.currentTargetCoord = targetCoord;

        if (targetCoord == null) {
            navigationMessage.postValue("목적지에 도착했습니다.");
            audioService.speak("목적지에 도착했습니다. 안내를 종료합니다.");
            fullRouteSegments.clear();
            setGuidingState(false);
            return;
        }

        double dLon = Math.toRadians(targetCoord.get("lng") - curLng);
        double lat1Rad = Math.toRadians(curLat);
        double lat2Rad = Math.toRadians(targetCoord.get("lat"));

        double y = Math.sin(dLon) * Math.cos(lat2Rad);
        double x = Math.cos(lat1Rad) * Math.sin(lat2Rad) - Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);

        double targetBearing = Math.toDegrees(Math.atan2(y, x));
        targetBearing = (targetBearing + 360.0) % 360.0; // 0~360 대응 정규화

        double currentYawVal = currentYaw.getValue() != null ? currentYaw.getValue() : 0.0;
        double error = targetBearing - currentYawVal;

        if (error > 180.0) error -= 360.0;
        if (error < -180.0) error += 360.0;

        angleError.postValue(error);
        updateBleManagerTxContext(); // 💡 라즈베리파이 백그라운드 스레드 제어기 데이터 싱크업

        if (Math.abs(error) <= 5.0) {
            navigationMessage.postValue("직진 하세요.");
        } else if (error > 5.0) {
            navigationMessage.postValue("오른쪽으로 " + String.format("%.1f", error) + "도 회전 하세요.");
        } else {
            navigationMessage.postValue("왼쪽으로 " + String.format("%.1f", Math.abs(error)) + "도 회전 하세요.");
        }
    }

    private Map<String, Double> getValidTargetCoordinate() {
        while (currentSegmentIndex < fullRouteSegments.size()) {
            RouteSegment segment = fullRouteSegments.get(currentSegmentIndex);
            List<Map<String, Double>> coords = segment.getCoords();

            while (currentCoordIndex < coords.size()) {
                Map<String, Double> coord = coords.get(currentCoordIndex);
                double distance = getDistance(curLat, curLng, coord.get("lat"), coord.get("lng"));

                if (distance < 5.0) {
                    currentCoordIndex++;
                } else {
                    return coord;
                }
            }
            currentSegmentIndex++;
            currentCoordIndex = 0;
        }
        return null;
    }

    private double getDistance(double lat1, double lon1, double lat2, double lon2) {
        double theta = lon1 - lon2;
        double dist = Math.sin(Math.toRadians(lat1)) * Math.sin(Math.toRadians(lat2))
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) * Math.cos(Math.toRadians(theta));
        dist = Math.acos(dist);
        dist = Math.toDegrees(dist);
        return dist * 60 * 1.1515 * 1609.344;
    }

    @Override
    protected void onCleared() {
        audioService.shutdown();
        BleManager.getInstance().disconnect();
        super.onCleared();
    }
}