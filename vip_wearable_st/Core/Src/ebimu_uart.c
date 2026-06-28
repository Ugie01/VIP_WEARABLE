/*
 * ebimu.c
 *
 *  Created on: Jun 23, 2026
 *      Author: KCCISTC
 */

/**
 * @brief DRV2605L 레지스터 쓰기 공통 함수
 */
#include "ebimu_uart.h"

HAL_StatusTypeDef EBIMU_Write(EBIMU_t *sensor, const char *cmd, uint8_t data) {
	char tx_buffer[40]; // <커맨드입력값>이 담길 임시 송신 버퍼

	// 1. <커맨드입력값> 형태로 문자열 포맷팅 및 안전한 버퍼 결합
	// 예: cmd가 "srp"이고 value가 10 이면 "<srp10>" 문자열 생성
	int len = snprintf(tx_buffer, sizeof(tx_buffer), "<%s%d>", cmd, data);

	// 2. 에러 가드: 버퍼 크기를 초과했거나 포맷팅 실패 시 전송 거부
	if (len < 0 || len >= (int) sizeof(tx_buffer)) {
		return HAL_ERROR;
	}

	// 3. 변환된 패킷 버퍼를 UART로 전송 (포맷팅된 문자열의 실제 길이인 len 사용)
	return HAL_UART_Transmit(sensor->huart, (uint8_t*) tx_buffer, strlen(tx_buffer), 1000);
}

/**
 * @brief DRV2605 레지스터 읽기 함수
 */
HAL_StatusTypeDef EBIMU_Read(EBIMU_t *sensor, uint16_t size) {
	// 수신 모드에 맞는 가변 크기 지정 수신
	return HAL_UART_Receive_DMA(sensor->huart, sensor->rx_Data, size);
}

HAL_StatusTypeDef EBIMU_Init(UART_HandleTypeDef *huart, EBIMU_t *sensor) {
	sensor->huart = huart;

	// 데이터 초기화
	sensor->roll = 0.0f;
	sensor->pitch = 0.0f;
	sensor->yaw = 0.0f;
	sensor->SET_OUTPUT_CODE = 2; // 기본 HEX 모드로 가정

	memset(sensor->rx_Data, 0, sizeof(sensor->rx_Data));

	return EBIMU_Read(sensor, 10);
}

HAL_StatusTypeDef EBIMU_Get_Euler_Angle(EBIMU_t *sensor) {
	if (sensor->SET_OUTPUT_CODE == 1) {
		// 버퍼 내에서 패킷의 시작점인 '*' 문자 검색
		char *pStart = strchr((char*) sensor->rx_Data, '*');
		if (pStart == NULL) {
			return HAL_ERROR; // 시작 문자가 없으면 파싱 거부
		}

		float t_roll = 0.0f, t_pitch = 0.0f, t_yaw = 0.0f;
		float t_acc_x = 0.0f, t_acc_y = 0.0f, t_acc_z = 0.0f;
		float t_gyro_x = 0.0f, t_gyro_y = 0.0f, t_gyro_z = 0.0f;

		// sscanf를 이용하여 포맷팅 파싱 (성공적으로 9개의 인자를 읽었는지 검증)
		// 포맷 문자열 "*%f,%f,%f"를 통해 '*' 건너뛰고 콤마 기준으로 변환
		int parsed_cnt = sscanf(pStart, "*%f,%f,%f,%f,%f,%f,%f,%f,%f", &t_roll, &t_pitch, &t_yaw, &t_gyro_x, &t_gyro_y, &t_gyro_z, &t_acc_x, &t_acc_y, &t_acc_z);

		if (parsed_cnt == 9) {
			// 정확히 3개의 데이터가 파싱된 경우에만 가변 데이터 최종 업데이트
			sensor->roll = t_roll;
			sensor->pitch = t_pitch;
			sensor->yaw = t_yaw;

			sensor->acc_x = t_acc_x;
			sensor->acc_y = t_acc_y;
			sensor->acc_z = t_acc_z;

			sensor->gyro_x = t_gyro_x;
			sensor->gyro_y = t_gyro_y;
			sensor->gyro_z = t_gyro_z;
			return HAL_OK;
		}
	} else if (sensor->SET_OUTPUT_CODE == 2) {
		EBIMU_Packet_t *packet = NULL;
		uint8_t *pValidData = NULL;
		// 전체 버퍼 만큼 돌면서 0x55, 0x55 패턴 매칭점 찾기
		for (uint8_t i = 0; i <= (SIZE - 22); i++) {
			if (sensor->rx_Data[i] == 0x55 && sensor->rx_Data[i + 1] == 0x55) {
				// 동기화 헤더를 찾았으므로 해당 포인터 저장
				pValidData = &sensor->rx_Data[i];
				packet = (EBIMU_Packet_t*) pValidData;
				break;
			}
		}

		// 헤더를 찾지 못했다면 에러 리턴
		if (packet == NULL) {
			return HAL_ERROR;
		}

		// 찾아낸 헤더 위치 기준으로 체크섬 검증 진행
		uint16_t calculated_chk = 0;
		for (uint8_t j = 0; j < 20; j++)
			calculated_chk += pValidData[j];

		if (calculated_chk != __REV16(packet->checksum)) {
			return HAL_ERROR; // 체크섬이 깨졌다면 데이터 버림
		}

		// 각도 데이터 정수형 필드 바이트 스왑 및 스케일링 (/100.0)
		int16_t r_raw = (int16_t) __REV16((uint16_t) packet->roll_raw);
		int16_t p_raw = (int16_t) __REV16((uint16_t) packet->pitch_raw);
		int16_t y_raw = (int16_t) __REV16((uint16_t) packet->yaw_raw);

		sensor->roll = (float) r_raw / 100.0f;
		sensor->pitch = (float) p_raw / 100.0f;
		sensor->yaw = (float) y_raw / 100.0f;

		// 자이로(각속도) 데이터 정수형 필드 바이트 스왑 및 스케일링 (/10.0)
		int16_t gx_raw = (int16_t) __REV16((uint16_t) packet->gyro_x_raw);
		int16_t gy_raw = (int16_t) __REV16((uint16_t) packet->gyro_y_raw);
		int16_t gz_raw = (int16_t) __REV16((uint16_t) packet->gyro_z_raw);

		sensor->gyro_x = (float) gx_raw / 10.0f;
		sensor->gyro_y = (float) gy_raw / 10.0f;
		sensor->gyro_z = (float) gz_raw / 10.0f;

		// 가속도 데이터 정수형 필드 바이트 스왑 및 스케일링 (/1000.0)
		int16_t ax_raw = (int16_t) __REV16((uint16_t) packet->acc_x_raw);
		int16_t ay_raw = (int16_t) __REV16((uint16_t) packet->acc_y_raw);
		int16_t az_raw = (int16_t) __REV16((uint16_t) packet->acc_z_raw);

		sensor->acc_x = (float) ax_raw / 1000.0f;
		sensor->acc_y = (float) ay_raw / 1000.0f;
		sensor->acc_z = (float) az_raw / 1000.0f;

		return HAL_OK;
	}

	return HAL_ERROR;
}

HAL_StatusTypeDef EBIMU_OUTPUT_ASCII(EBIMU_t *sensor) {
	sensor->SET_OUTPUT_CODE = 1;
	HAL_UART_DMAStop(sensor->huart); // 기존 DMA 중지 후 재설정
	EBIMU_Write(sensor, "soc", 1);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_OUTPUT_HEX(EBIMU_t *sensor) {
	sensor->SET_OUTPUT_CODE = 2;
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "soc", 2);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_FORMAT_EulerAngles(EBIMU_t *sensor) {
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "sof", 1);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_FORMAT_Quaternion(EBIMU_t *sensor) {
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "sof", 2);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_SET_GYRO(EBIMU_t *sensor) {
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "sog", 1);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_RESET_GYRO(EBIMU_t *sensor) {
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "sog", 0);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

/*
 0: 가속도데이터 출력 안함
 1: 가속도데이터 출력
 2: 중력성분 제거된 가속도 출력 (Local)
 3: 중력성분 제거된 가속도 출력 (Global)
 4: 속도데이터 출력 (Local)
 5: 속도데이터 출력 (Global)
 */
HAL_StatusTypeDef EBIMU_RESET_ACCELERO(EBIMU_t *sensor, uint8_t value) {
	HAL_UART_DMAStop(sensor->huart);
	EBIMU_Write(sensor, "soa", value);
	memset(sensor->rx_Data, 0, SIZE);
	return EBIMU_Read(sensor, SIZE);
}

