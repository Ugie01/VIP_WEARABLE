package com.example.vip_wearable_java;

import android.os.Bundle;
import android.widget.Button;
import android.widget.SeekBar;
import androidx.appcompat.app.AppCompatActivity;
import com.example.vip_wearable_java.services.AudioService;
import com.example.vip_wearable_java.R;
import com.example.vip_wearable_java.utils.PreferenceManager;

public class AudioSettingsActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_audio_settings);

        SeekBar sbRate = findViewById(R.id.sb_rate);
        SeekBar sbVolume = findViewById(R.id.sb_volume);
        SeekBar sbPitch = findViewById(R.id.sb_pitch);
        Button btnSave = findViewById(R.id.btn_save);

        // 현재 전역 주입된 싱글톤 AudioService 속도 값을 디폴트로 세팅 (초기 바인딩 보정)
        AudioService audioService = AudioService.getInstance(this);
        int currentProgress = (int) ((audioService.getRate() - 0.2f) * 10.0f);
        sbRate.setProgress(currentProgress);

        btnSave.setOnClickListener(v -> {
            // UI 크기 슬라이더(SeekBar) 값 파싱 정밀 연산 (예시)
            float selectedVolume = sbVolume.getProgress() / 10.0f;
            float speedRate = (sbRate.getProgress() / 10.0f) + 0.2f; // [cite: 13]
            float voicePitch = (sbPitch.getProgress() / 10.0f) + 0.5f; // 0.5 ~ 1.5 톤 범위 제어

            // 1. 싱글톤 오디오 엔진에 즉시 설정 변경 파라미터 업데이트 전달 [cite: 13]
            audioService.setParams(selectedVolume, speedRate, voicePitch);

            // 2. 디바이스 저장소에 저장하여 재구동 시에도 값 유지 보장 [cite: 46]
            PreferenceManager.saveAudioParams(this, selectedVolume, speedRate, voicePitch);

            finish(); // [cite: 13]
        });
    }
}