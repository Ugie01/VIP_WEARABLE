package com.example.vip_wearable_java;

import android.os.Bundle;
import android.widget.Button;
import android.widget.SeekBar;
import android.widget.Toast;

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

        AudioService audioService = AudioService.getInstance(this);
        int currentProgress = (int) ((audioService.getRate() - 0.2f) * 10.0f);
        sbRate.setProgress(currentProgress);

        btnSave.setOnClickListener(v -> {
            float selectedVolume = sbVolume.getProgress() / 10.0f;
            float speedRate = (sbRate.getProgress() / 10.0f) + 0.2f;
            float voicePitch = (sbPitch.getProgress() / 10.0f) + 0.5f;

            audioService.setParams(selectedVolume, speedRate, voicePitch);

            PreferenceManager.saveAudioParams(this, selectedVolume, speedRate, voicePitch);

            finish();
        });

        Button btnResetBle = findViewById(R.id.btn_reset_ble);
        if (btnResetBle != null) {
            btnResetBle.setOnClickListener(v -> {
                PreferenceManager.clearBleDeviceAddress(this);
                Toast.makeText(this, "BLE 기기 연결 기록이 초기화되었습니다.", Toast.LENGTH_SHORT).show();
            });
        }
    }
}