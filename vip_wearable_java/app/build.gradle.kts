import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.vip_wearable_java"
    compileSdk = 36 // 표준 정수형 컴파일 SDK 지정 방식을 권장합니다.

    defaultConfig {
        applicationId = "com.example.vip_wearable_java"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // local.properties에서 안전하게 키 로드
        val properties = Properties()
        val localPropertiesFile = project.rootProject.file("local.properties")
        if (localPropertiesFile.exists()) {
            properties.load(localPropertiesFile.inputStream())
        }
        val tmapApiKey = properties.getProperty("TMAP_API_KEY") ?: ""
        buildConfigField("String", "TMAP_API_KEY", "\"$tmapApiKey\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false // Kotlin DSL 표준 최적화/난독화 플래그 표현식으로 보정
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    // 중복 제거 및 버전 카탈로그 통합 관리
    implementation(libs.activity.ktx)
    implementation(libs.appcompat)
    implementation(libs.constraintlayout)
    implementation(libs.material)

    testImplementation(libs.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(libs.ext.junit)

    // 위치 서비스 (GPS)
    implementation("com.google.android.gms:play-services-location:21.0.1")

    // TMAP 핵심 파일 직접 매핑 (로컬 aar 의존성)
    implementation(files("libs/tmap-sdk-3.6.aar"))
    implementation(files("libs/vsm-tmap-sdk-v2-eaa-2.0.14.aar"))

    // 네트워크 및 JSON 파싱 (Retrofit / Gson)
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.11.0")

    // 비동기/라이프사이클 관리 (Jetpack)
    implementation("androidx.lifecycle:lifecycle-viewmodel:2.6.2")
    implementation("androidx.lifecycle:lifecycle-livedata:2.6.2")
    implementation("com.google.code.gson:gson:2.10.1")
}