package com.example.vip_wearable_java.services;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;


public class TmapService {
    private final String appKey;
    private final OkHttpClient client = new OkHttpClient();

    public TmapService(String appKey) {
        this.appKey = appKey;
    }

    public interface TmapCallback<T> {
        void onSuccess(T result);
        void onFailure(Exception e);
    }

    public void searchPoi(String keyword, TmapCallback<Map<String, Object>> callback) {
        String url = "https://apis.openapi.sk.com/tmap/pois?version=1&searchKeyword=" + keyword + "&resCoordType=WGS84GEO&reqCoordType=WGS84GEO&count=1";
        Request request = new Request.Builder().url(url).addHeader("appKey", appKey).build();

        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) { callback.onFailure(e); }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (!response.isSuccessful()) { callback.onFailure(new IOException("Unexpected code " + response)); return; }
                try {
                    JsonObject json = new JsonParser().parse(response.body().string()).getAsJsonObject();
                    JsonObject poi = json.getAsJsonObject("searchPoiInfo").getAsJsonObject("pois").getAsJsonArray("poi").get(0).getAsJsonObject();
                    Map<String, Object> result = new HashMap<>();
                    result.put("lat", Double.parseDouble(poi.get("noorLat").getAsString()));
                    result.put("lng", Double.parseDouble(poi.get("noorLon").getAsString()));
                    result.put("name", poi.get("name").getAsString());
                    callback.onSuccess(result);
                } catch (Exception e) { callback.onFailure(e); }
            }
        });
    }

    // 보도자 주행 경로 데이터 fetch 기능 이식 구현
    public void fetchPedestrianRoute(double startLat, double startLng, double endLat, double endLng, String endName, TmapCallback<List<com.example.vip_wearable_java.models.RouteSegment>> callback) {
        String url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1";
        JsonObject jsonBody = new JsonObject();
        jsonBody.addProperty("startX", startLng);
        jsonBody.addProperty("startY", startLat);
        jsonBody.addProperty("endX", endLng);
        jsonBody.addProperty("endY", endLat);
        jsonBody.addProperty("startName", "출발지");
        jsonBody.addProperty("endName", endName);

        RequestBody body = RequestBody.create(jsonBody.toString(), MediaType.parse("application/json; charset=utf-8"));
        Request request = new Request.Builder().url(url).addHeader("appKey", appKey).post(body).build();

        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) { callback.onFailure(e); }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (!response.isSuccessful()) { callback.onFailure(new IOException("Error")); return; }
                try {
                    List<com.example.vip_wearable_java.models.RouteSegment> segments = new ArrayList<>();
                    JsonObject json = new JsonParser().parse(response.body().string()).getAsJsonObject();
                    JsonArray features = json.getAsJsonArray("features");
                    String currentFacilityType = "11";

                    for (int i = 0; i < features.size(); i++) {
                        JsonObject feature = features.get(i).getAsJsonObject();
                        JsonObject geometry = feature.getAsJsonObject("geometry");
                        JsonObject properties = feature.getAsJsonObject("properties");
                        String type = geometry.get("type").getAsString();

                        if (type.equals("Point") && properties != null) {
                            if (properties.has("facilityType")) currentFacilityType = properties.get("facilityType").getAsString();
                        } else if (type.equals("LineString")) {
                            JsonArray coords = geometry.getAsJsonArray("coordinates");
                            String color = "#FF0000"; // 기본 인도 없는 인프라구간 정적 표기값
                            if (currentFacilityType.equals("11") || currentFacilityType.equals("12")) color = "#FFFF00";
                            else if (currentFacilityType.equals("15")) color = "#00FF00";
                            else if (currentFacilityType.equals("17")) color = "#8A2BE2";

                            List<Map<String, Double>> singleCoords = new ArrayList<>();
                            for (int j = 0; j < coords.size(); j++) {
                                JsonArray c = coords.get(j).getAsJsonArray();
                                Map<String, Double> pt = new HashMap<>();
                                pt.put("lng", c.get(0).getAsDouble());
                                pt.put("lat", c.get(1).getAsDouble());
                                singleCoords.add(pt);
                            }
                            segments.add(new com.example.vip_wearable_java.models.RouteSegment(color, singleCoords));
                        }
                    }
                    callback.onSuccess(segments);
                } catch (Exception e) { callback.onFailure(e); }
            }
        });
    }
}