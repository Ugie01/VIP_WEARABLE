/*
 * dev2605_i2c.c
 *
 *  Created on: Jun 21, 2026
 *      Author: ugie01
 */

#include <drv2605_i2c.h>

// DRV2605L 레지스터 쓰기 공통 함수
HAL_StatusTypeDef DRV2605L_WriteRegister(DRV2605L_t *sensor, uint8_t regAddr, uint8_t data) {
	return HAL_I2C_Mem_Write(sensor->hi2c, DRV2605L_ADDR, regAddr, I2C_MEMADD_SIZE_8BIT, &data, 1, 1000);
}

// DRV2605 레지스터 읽기 함수
HAL_StatusTypeDef DRV2605_ReadRegister(DRV2605L_t *sensor, uint8_t regAddr, uint8_t *pData) {
	return HAL_I2C_Mem_Read(sensor->hi2c, DRV2605L_ADDR, regAddr, I2C_MEMADD_SIZE_8BIT, pData, 1, HAL_MAX_DELAY);
}

// DRV2605L 초기화 함수 (I2C 핸들러 및 구조체 동적 매핑)
HAL_StatusTypeDef DRV2605L_Init(I2C_HandleTypeDef *hi2c, DRV2605L_t *sensor) {
	HAL_StatusTypeDef status;

	// 전달받은 I2C 핸들러 주소를 구조체에 할당 (I2C 채널 가변 대응)
	sensor->hi2c = hi2c;

	// 소프트웨어 리셋 수행 (0x01 레지스터에 DEV_RESET Bit[7]=1 쓰기)
	status = DRV2605L_WriteRegister(sensor, REG_MODE, 0x80);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}
	// 리셋 후 칩이 안정화될 때까지 짧은 대기 (최소 수 ms 필요)
	HAL_Delay(20);

	// 대기 모드 해제 및 내부 트리거 모드 설정 (REG_MODE = 0x00)
	status = DRV2605L_WriteRegister(sensor, REG_MODE, 0x00);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}
	HAL_Delay(20);

	// 모터 기본 타입 설정 (REG_FEEDBACK_CTRL = 0x36, ERM 기본값)
	status = DRV2605L_WriteRegister(sensor, REG_FEEDBACK_CTRL, 0x36);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}
	HAL_Delay(20);

	// 내장 라이브러리 선택 (REG_LIBRARY_SEL = 0x01, ERM 라이브러리 A)
	status = DRV2605L_WriteRegister(sensor, REG_LIBRARY_SEL, 0x01);
	if (status != HAL_OK) {
		return HAL_ERROR;
	}
	HAL_Delay(20);

	return HAL_OK;
}

// 특정 햅틱 효과 재생 함수
// sensor: 제어할 센서 인스턴스 포인터
// effectNum: 햅틱 라이브러리 효과 번호 (1 ~ 123)
HAL_StatusTypeDef DRV2605L_PlayEffect(DRV2605L_t *sensor, uint8_t effectNum) {
	HAL_StatusTypeDef status;

//	파형 시퀀서 1번에 효과 번호 등록
	status = DRV2605L_WriteRegister(sensor, REG_WAV_SEQ1, effectNum);
	if (status != HAL_OK)
		return HAL_ERROR;

//	파형 시퀀서 2번에 0을 넣어 시퀀스 종료 지정
	status = DRV2605L_WriteRegister(sensor, REG_WAV_SEQ2, 0x00);
	if (status != HAL_OK)
		return HAL_ERROR;

//	GO 레지스터 트리거 (햅틱 진동 시작)
	status = DRV2605L_WriteRegister(sensor, REG_GO, 0x01);
	if (status != HAL_OK)
		return HAL_ERROR;

	return HAL_OK;
}

// 생체 피드백 입력값(-100 ~ 100)에 따라 좌우 햅틱 모터의 세기를 실시간 제어하는 함수
// sensor_L: 왼쪽 모터 DRV2605L 인스턴스 포인터
// sensor_R: 오른쪽 모터 DRV2605L 인스턴스 포인터
// feedback_value: -100 ~ 100 사이의 방향/편차 입력값
HAL_StatusTypeDef DRV2605L_UpdateHapticFeedback(DRV2605L_t *sensor_L, DRV2605L_t *sensor_R, int16_t feedback_value) {
	HAL_StatusTypeDef status;
	uint8_t left_intensity = 0;
	uint8_t right_intensity = 0;

//	입력값 범위 리미트 처리 (-100 ~ 100 가드)
	if (feedback_value < -100)
		feedback_value = -100;
	if (feedback_value > 100)
		feedback_value = 100;

//	방향 및 세기 분기 매핑 연산
	if (feedback_value < -3.0) {
//		-100에 가까울수록 왼쪽이 강해짐 (오른쪽은 OFF)
		int16_t abs_value = -feedback_value;
		left_intensity = (uint8_t) ((abs_value * HAPTIC_MAX_INTENSITY) / 100);
		right_intensity = 0;
	} else if (feedback_value > 3.0) {
//		100에 가까울수록 오른쪽이 강해짐 (왼쪽은 OFF)
		left_intensity = 0;
		right_intensity = (uint8_t) ((feedback_value * HAPTIC_MAX_INTENSITY) / 100);
	} else {
//		정중앙 타겟 지점 도달 시 양쪽 모두 진동 종료
		left_intensity = 0;
		right_intensity = 0;
	}

	// 두 드라이버 칩을 RTP 모드(0x05)로 동기화 유지
	status = DRV2605L_WriteRegister(sensor_L, REG_MODE, 0x05);
	if (status != HAL_OK)
		return HAL_ERROR;

	status = DRV2605L_WriteRegister(sensor_R, REG_MODE, 0x05);
	if (status != HAL_OK)
		return HAL_ERROR;

//	각 칩의 실시간 재생 레지스터에 계산된 세기 값 반영
//	MODE[2:0] = 5 (RTP 모드)일 때 RTP_INPUT[7:0] 값을 부하로 전달
	status = DRV2605L_WriteRegister(sensor_L, REG_RTP_INPUT, left_intensity);
	if (status != HAL_OK)
		return HAL_ERROR;

	status = DRV2605L_WriteRegister(sensor_R, REG_RTP_INPUT, right_intensity);
	if (status != HAL_OK)
		return HAL_ERROR;

	return HAL_OK;
}

HAL_StatusTypeDef DRV2605L_Reconnect(DRV2605L_t *sensor) {
	printf("\r\n[경고] DRV2605L I2C 통신 끊김 감지! 재연결 시도 중...\r\n");

	GPIO_InitTypeDef GPIO_InitStruct = { 0 };
	GPIO_TypeDef *scl_port = NULL;
	GPIO_TypeDef *sda_port = NULL;
	uint16_t scl_pin = 0;
	uint16_t sda_pin = 0;

	// 센서의 I2C 채널 판별 및 해당 GPIO/하드웨어 매크로 가변 매핑
	if (sensor->hi2c->Instance == I2C2) {
		// I2C2 매핑 팩트: SCL = PB10, SDA = PB9
		__HAL_RCC_GPIOB_CLK_ENABLE();
		scl_port = GPIOB;
		scl_pin = GPIO_PIN_10;
		sda_port = GPIOB;
		sda_pin = GPIO_PIN_9;
	} else if (sensor->hi2c->Instance == I2C3) {
		// I2C3 매핑 팩트: SCL = PA8, SDA = PC9
		__HAL_RCC_GPIOA_CLK_ENABLE();
		__HAL_RCC_GPIOC_CLK_ENABLE();
		scl_port = GPIOA;
		scl_pin = GPIO_PIN_8;
		sda_port = GPIOC;
		sda_pin = GPIO_PIN_9;
	} else {
		printf("[에러] 지원하지 않는 I2C 채널입니다.\r\n");
		return HAL_ERROR;
	}

	// 강제 Bus 클리어 (SCL 토글을 위해 GPIO Open-Drain Output 설정)
	GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
	GPIO_InitStruct.Pull = GPIO_PULLUP;
	GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;

	GPIO_InitStruct.Pin = scl_pin;
	HAL_GPIO_Init(scl_port, &GPIO_InitStruct);

	GPIO_InitStruct.Pin = sda_pin;
	HAL_GPIO_Init(sda_port, &GPIO_InitStruct);

	// SCL 16회 토글 수행 (슬레이브가 붙잡고 있는 SDA 라인 릴리즈 유도)
	for (int i = 0; i < 16; i++) {
		HAL_GPIO_WritePin(scl_port, scl_pin, GPIO_PIN_RESET);
		HAL_Delay(1);
		HAL_GPIO_WritePin(scl_port, scl_pin, GPIO_PIN_SET);
		HAL_Delay(1);
	}

	// STOP 조건 강제 생성 (SCL이 High인 상태에서 SDA를 Low에서 High로 변경)
	HAL_GPIO_WritePin(sda_port, sda_pin, GPIO_PIN_RESET);
	HAL_Delay(1);
	HAL_GPIO_WritePin(scl_port, scl_pin, GPIO_PIN_SET);
	HAL_Delay(1);
	HAL_GPIO_WritePin(sda_port, sda_pin, GPIO_PIN_SET);
	HAL_Delay(5);

	// 사용한 GPIO 핀 원상복구 (DeInit)
	HAL_GPIO_DeInit(scl_port, scl_pin);
	HAL_GPIO_DeInit(sda_port, sda_pin);

	// STM32 I2C 하드웨어 내부 레지스터 강제 리셋 및 HAL 구조체 해제
	HAL_I2C_DeInit(sensor->hi2c);

	if (sensor->hi2c->Instance == I2C2) {
		__HAL_RCC_I2C2_FORCE_RESET();
		HAL_Delay(30);
		__HAL_RCC_I2C2_RELEASE_RESET();
		HAL_Delay(30);
		MX_I2C2_Init(); // STM32CubeIDE가 생성한 초기화 함수 재호출
	} else if (sensor->hi2c->Instance == I2C3) {
		__HAL_RCC_I2C3_FORCE_RESET();
		HAL_Delay(30);
		__HAL_RCC_I2C3_RELEASE_RESET();
		HAL_Delay(30);
		MX_I2C3_Init(); // STM32CubeIDE가 생성한 초기화 함수 재호출
	}

	// 	드라이버 레지스터 재설정 및 연결 상태 검증
	if (DRV2605L_Init(sensor->hi2c, sensor) == HAL_OK) { //
		printf("[성공] 드라이버 재연결 완료. 정상 제어를 재개합니다.\r\n\r\n");
		return HAL_OK;
	} else {
		printf("[실패] 드라이버가 응답하지 않습니다. 물리 연결이나 전원을 확인하세요.\r\n\r\n");
		return HAL_ERROR;
	}
}
