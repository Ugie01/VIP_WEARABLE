/*
 * fall_detection.c
 *
 *  Created on: Jun 23, 2026
 *      Author: KCCISTC
 */

#include "fall_detection.h"
#include <math.h>

/*
 내부 튜닝 파라미터 (상수 정의)
 FALL_LOW_THRESHOLD (기본값: 0.5f)
 센서가 아래로 떨어질 때 무중력 상태에 가까워지는 것을 포착하는 값입니다.
 값이 너무 크면(0.7f 등) 계단을 내려가거나 몸을 살짝 숙이는 동작에도 자유낙하로 오탐지할 수 있고, 너무 작으면(0.3f 등) 실제 낙하 시 감지를 놓칠 수 있습니다.

 FALL_HIGH_THRESHOLD (기본값: 2.5f)
 바닥에 쾅 하고 부딪히는 순간의 충격량 임계값입니다.
 침대에 눕거나 주저앉는 일상 동작에서 자꾸 낙상으로 오탐지된다면 이 값을 3.0f 이상으로 올려야 하며, 센서가 두꺼운 옷 위에 정렬되어 충격이 흡수된다면 2.0f 부근으로 낮춰야 합니다.

 FALL_GYRO_THRESHOLD (기본값: 150.0f)
 넘어질 때 몸이 휘청거리며 발생하는 회전 속도 기준입니다.
 */

#define FALL_LOW_THRESHOLD   0.5f
#define FALL_HIGH_THRESHOLD  2.5f
#define FALL_GYRO_THRESHOLD  150.0f

// 외부에서 접근 못 하도록 static 가드 처리한 내부 상태 변수
static FallState_t fall_state = FALL_STATE_IDLE;
static uint32_t fall_timer = 0;
float svm = 0.0f, gvm = 0.0f;

void FallDetection_Init(void) {
	fall_state = FALL_STATE_IDLE;
	fall_timer = 0;
}

uint8_t FallDetection_Update(EBIMU_t *sensor) {
	// 3축 가속도 및 자이로 벡터 합산 크기 계산
	svm = sqrtf((sensor->acc_x * sensor->acc_x) + (sensor->acc_y * sensor->acc_y) + (sensor->acc_z * sensor->acc_z));
	gvm = sqrtf((sensor->gyro_x * sensor->gyro_x) + (sensor->gyro_y * sensor->gyro_y) + (sensor->gyro_z * sensor->gyro_z));

	uint32_t current_tick = HAL_GetTick();

	switch (fall_state) {
	case FALL_STATE_IDLE:
		if (svm < FALL_LOW_THRESHOLD) {
			fall_state = FALL_STATE_FREEFALL;
			fall_timer = current_tick;
		}
		break;

	case FALL_STATE_FREEFALL:
		if (current_tick - fall_timer > 500) {
			fall_state = FALL_STATE_IDLE;
		} else {
			if (svm > FALL_HIGH_THRESHOLD && gvm > FALL_GYRO_THRESHOLD) {
				fall_state = FALL_STATE_IMPACT;
				fall_timer = current_tick;
			}
		}
		break;

	case FALL_STATE_IMPACT:
		if (current_tick - fall_timer > 1000) {
			// 최종 정지 및 누워있는 상태 검증 후 낙상 확정
			if (gvm < 15.0f && svm > 0.8f && svm < 1.2f) {
				fall_state = FALL_STATE_IDLE;
				return 1;
			}
			fall_state = FALL_STATE_IDLE;
		}
		break;
	}
	return 0;
}
