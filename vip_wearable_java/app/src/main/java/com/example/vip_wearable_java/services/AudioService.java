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
    private AudioManager audioManager;
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

        this.volume = PreferenceManager.getVolume(context);
        this.rate = PreferenceManager.getRate(context);
        this.pitch = PreferenceManager.getPitch(context);

        tts = new TextToSpeech(context, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.KOREAN);
                isInitialized = true;
                applySettings();
            }
        });
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context);
    }

    private void applySettings() {
        if (!isInitialized) return;
        tts.setSpeechRate(rate);
        tts.setPitch(pitch);
    }

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
    private void updateVolumeFromSystem() {
        if (audioManager != null) {
            float currentVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
            float maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
            if (maxVol > 0) {
                this.volume = currentVol / maxVol;
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

        updateVolumeFromSystem();
        Bundle params = new Bundle();
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