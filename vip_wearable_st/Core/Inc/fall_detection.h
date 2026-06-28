/*
 * fall_detection.h
 *
 *  Created on: Jun 23, 2026
 *      Author: KCCISTC
 */

#ifndef INC_FALL_DETECTION_H_
#define INC_FALL_DETECTION_H_

#include "main.h"
#include "ebimu_uart.h" // IMU 데이터 구조체 참조용

// 낙상 감지 상태 정의
typedef enum {
	FALL_STATE_IDLE, FALL_STATE_FREEFALL, FALL_STATE_IMPACT
} FallState_t;

// 함수 선언
void FallDetection_Init(void);
uint8_t FallDetection_Update(EBIMU_t *sensor);

#endif /* INC_FALL_DETECTION_H_ */
