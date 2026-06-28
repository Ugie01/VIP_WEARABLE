package com.example.vip_wearable_java.models;

import java.util.List;
import java.util.Map;

public class RouteSegment {
    private String color;
    private List<Map<String, Double>> coords;

    public RouteSegment(String color, List<Map<String, Double>> coords) {
        this.color = color;
        this.coords = coords;
    }

    public String getColor() { return color; }
    public List<Map<String, Double>> getCoords() { return coords; }
}