package com.example.vip_wearable_java.utils;

import android.content.Context;
import android.content.SharedPreferences;
import com.example.vip_wearable_java.config.AppConfig;

public class PreferenceManager {
    private static final String PREF_NAME = "audio_settings_pref";

    public static void saveAudioParams(Context context, float volume, float rate, float pitch) {
        SharedPreferences pref = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        SharedPreferences.Editor editor = pref.edit();
        editor.putFloat("volume", volume);
        editor.putFloat("rate", rate);
        editor.putFloat("pitch", pitch);
        editor.apply();
    }

    public static float getVolume(Context context) {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
                .getFloat("volume", AppConfig.DEFAULT_AUDIO_VOLUME);
    }

    public static float getRate(Context context) {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
                .getFloat("rate", AppConfig.DEFAULT_AUDIO_RATE);
    }

    public static float getPitch(Context context) {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
                .getFloat("pitch", AppConfig.DEFAULT_AUDIO_PITCH);
    }
}