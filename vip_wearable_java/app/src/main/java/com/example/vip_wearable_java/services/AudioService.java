package com.example.vip_wearable_java.services;

import android.content.Context;
import android.content.Intent;
import android.media.AudioManager; // 💡 시스템 볼륨 취득을 위해 추가
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;

import com.example.vip_wearable_java.utils.PreferenceManager;

import java.util.ArrayList;
import java.util.Locale;


public class AudioService {
    private static volatile AudioService instance;
    private TextToSpeech tts;
    private SpeechRecognizer speechRecognizer;
    private AudioManager audioManager; // 💡 시스템 오디오 매니저 추가
    private float volume = 1.0f;
    private float rate = 0.5f;
    private float pitch = 1.0f;
    private boolean isInitialized = false;

    public interface SpeechCallback {
        void onResult(String text);
        void onStatusChange(boolean isListening);
    }

    public static AudioService getInstance(Context context) {
        if (instance == null) {
            synchronized (AudioService.class) {
                if (instance == null) {
                    instance = new AudioService(context.getApplicationContext());
                }
            }
        }
        return instance;
    }

    public AudioService(Context context) {
        audioManager = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);

        // 💡 [개선] 초기화 시 시스템 볼륨 비율 대신, 저장되어 있던 사용자 커스텀 오디오 설정을 로드합니다. [cite: 15]
        this.volume = PreferenceManager.getVolume(context);
        this.rate = PreferenceManager.getRate(context);
        this.pitch = PreferenceManager.getPitch(context);

        tts = new TextToSpeech(context, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.KOREAN);
                isInitialized = true;
                applySettings(); // 로드된 속도(rate)와 톤(pitch)을 TTS 엔진에 즉시 바인딩 [cite: 15]
            }
        });
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context);
    }

    private void applySettings() {
        if (!isInitialized) return;
        tts.setSpeechRate(rate); // 빠르기 제어 [cite: 15]
        tts.setPitch(pitch);    // 목소리 톤(음높이) 제어 [cite: 15]
    }

    // 💡 파라미터에서 Context context를 제거합니다.
    public void startListening(SpeechCallback callback) {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR");

        speechRecognizer.setRecognitionListener(new RecognitionListener() {
            @Override public void onReadyForSpeech(Bundle params) { callback.onStatusChange(true); }
            @Override public void onBeginningOfSpeech() {}
            @Override public void onRmsChanged(float rmsdB) {}
            @Override public void onBufferReceived(byte[] buffer) {}
            @Override public void onEndOfSpeech() { callback.onStatusChange(false); }
            @Override public void onError(int error) { callback.onStatusChange(false); }
            @Override public void onResults(Bundle results) {
                ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                if (matches != null && !matches.isEmpty()) { callback.onResult(matches.get(0)); }
            }
            @Override public void onPartialResults(Bundle partialResults) {}
            @Override public void onEvent(int eventType, Bundle params) {}
        });
        speechRecognizer.startListening(intent);
    }
    // 💡 2. 핸드폰 현재 설정 볼륨 비율을 가져오는 메서드 (0.0f ~ 1.0f)
    private void updateVolumeFromSystem() {
        if (audioManager != null) {
            float currentVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
            float maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
            if (maxVol > 0) {
                this.volume = currentVol / maxVol; // 현재 핸드폰 소리 크기 비율 반영
            }
        }
    }

    public void setParams(float vol, float rat, float pit) {
        this.volume = vol;
        this.rate = rat;
        this.pitch = pit;
        applySettings();
    }

    public void setMainRate(float rat) {
        this.rate = rat;
        applySettings();
    }

    public void speak(String text) {
        if (!isInitialized || tts == null) return;

        // 💡 3. 말하기 직전에 사용자가 핸드폰 버튼으로 소리를 바꿨을 수 있으므로 재동기화
        updateVolumeFromSystem();

        Bundle params = new Bundle();
        // 💡 핸드폰 기존 설정 소리(this.volume)를 파라미터로 강제 바인딩
        params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, this.volume);

        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, null);
    }

    public void stopListening() { speechRecognizer.stopListening(); }

    public void shutdown() {
        if (tts != null) tts.shutdown();
        if (speechRecognizer != null) speechRecognizer.destroy();
        instance = null;
    }

    public float getVolume() { return volume; }
    public float getRate() { return rate; }
    public float getPitch() { return pitch; }
}