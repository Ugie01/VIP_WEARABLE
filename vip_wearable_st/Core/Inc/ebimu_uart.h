/*
 * ebimu_uart.h
 *
 *  Created on: Jun 23, 2026
 *      Author: KCCISTC
 */

#ifndef INC_EBIMU_UART_H_
#define INC_EBIMU_UART_H_

#include "main.h"
#include "usart.h"
#include "gpio.h"

#include <string.h>
#include <stdio.h>

#define SIZE 80

typedef struct __attribute__((packed)) {
	uint16_t sop;          // 0x55, 0x55 (2바이트)

	// 오일러 각도
	int16_t roll_raw;     // 2바이트
	int16_t pitch_raw;    // 2바이트
	int16_t yaw_raw;      // 2바이트

	// 3축 자이로
	int16_t gyro_x_raw;       // 2바이트
	int16_t gyro_y_raw;       // 2바이트
	int16_t gyro_z_raw;       // 2바이트

	// 3축 가속도
	int16_t acc_x_raw;        // 2바이트
	int16_t acc_y_raw;        // 2바이트
	int16_t acc_z_raw;        // 2바이트

	uint16_t checksum;     // 체크섬 데이터 (2바이트)
} EBIMU_Packet_t; // 총 22바이트 고정 패킷

typedef struct {
	UART_HandleTypeDef *huart;

	uint8_t rx_Data[SIZE];
	uint16_t head;
	uint8_t SET_OUTPUT_CODE;
	uint8_t OUTPUT_DATA_FORMAT;

	// 파싱된 최종 오일러 각도 데이터 저장용 (단위: 도 °)
	float roll, pitch, yaw;
	// 파싱된 최종 3축 가속도 데이터 저장용 (단위: g 또는 m/s^2)
	float acc_x, acc_y, acc_z;
	// 파싱된 최종 3축 자이로(각속도) 데이터 저장용 (단위: °/s)
	float gyro_x, gyro_y, gyro_z;

} EBIMU_t;

HAL_StatusTypeDef EBIMU_Write(EBIMU_t *sensor, const char *cmd, uint8_t data);
HAL_StatusTypeDef EBIMU_Read(EBIMU_t *sensor, uint16_t size);
HAL_StatusTypeDef EBIMU_Init(UART_HandleTypeDef *huart, EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_Get_Euler_Angle(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_OUTPUT_ASCII(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_OUTPUT_HEX(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_FORMAT_EulerAngles(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_FORMAT_Quaternion(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_SET_GYRO(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_RESET_GYRO(EBIMU_t *sensor);
HAL_StatusTypeDef EBIMU_RESET_ACCELERO(EBIMU_t *sensor, uint8_t value);
#endif /* INC_EBIMU_UART_H_ */
