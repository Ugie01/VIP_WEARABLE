package com.example.vip_wearable_java.config;

public class AppConfig {
    // 1. 위치 및 가이드 관련 하이퍼파라미터
    public static final double DEFAULT_LAT = 37.555142; // 초기 디폴트 위도 [cite: 32]
    public static final double DEFAULT_LNG = 126.970448; // 초기 디폴트 경도 [cite: 32]
    public static final double TARGET_SWITCH_DISTANCE_METER = 5.0; // 다음 포인트 스위칭 거리 (역치)
    public static final double NAVIGATION_ANGLE_STRAIGHT_DEGREE = 15.0; // 직진 인정 오차 범위

    // 2. 오디오 기본 설정값
    public static final float DEFAULT_AUDIO_VOLUME = 1.0f; // 초기 볼륨 [cite: 15]
    public static final float DEFAULT_AUDIO_RATE = 1.0f;   // 기본 말하기 속도 (표준 1.0f 배속 권장)
    public static final float DEFAULT_AUDIO_PITCH = 1.0f;  // 기본 목소리 톤 (음높이) [cite: 15]
}