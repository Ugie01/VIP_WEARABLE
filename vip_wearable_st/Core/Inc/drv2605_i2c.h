/*
 * drv2605_i2c.h
 *
 *  Created on: Jun 21, 2026
 *      Author: ugie01
 */

#ifndef INC_QMC5883L_I2C_H_
#define INC_QMC5883L_I2C_H_

#include "main.h"
#include "i2c.h"
#include "gpio.h"

#include <stdio.h>

#define DRV2605L_ADDR        	(0x5A << 1)
// 주요 레지스터 주소 정의
#define REG_STATUS              0x00
#define REG_MODE                0x01
#define REG_RTP_INPUT           0x02
#define REG_LIBRARY_SEL         0x03
#define REG_WAV_SEQ1            0x04
#define REG_WAV_SEQ2            0x05
#define REG_GO                  0x0C
#define REG_FEEDBACK_CTRL       0x1A

#define HAPTIC_MAX_INTENSITY    64   // 최대 진동 세기 제한 (0 ~ 127 범위 내에서 설정 가능)
#define HAPTIC_UPDATE_PERIOD    50   // 햅틱 제어 주기 (단위: ms, 주기가 작을수록 실시간 반응성 향상)

typedef struct {
	I2C_HandleTypeDef *hi2c;

} DRV2605L_t;

HAL_StatusTypeDef DRV2605L_WriteRegister(DRV2605L_t *sensor, uint8_t regAddr, uint8_t data);
HAL_StatusTypeDef DRV2605_ReadRegister(DRV2605L_t *sensor, uint8_t regAddr, uint8_t *pData);
HAL_StatusTypeDef DRV2605L_Init(I2C_HandleTypeDef *hi2c, DRV2605L_t *sensor);
HAL_StatusTypeDef DRV2605L_PlayEffect(DRV2605L_t *sensor, uint8_t effectNum);
HAL_StatusTypeDef DRV2605L_UpdateHapticFeedback(DRV2605L_t *sensor_L, DRV2605L_t *sensor_R, int16_t feedback_value);
HAL_StatusTypeDef DRV2605L_Reconnect(DRV2605L_t *sensor);

#endif /* INC_QMC5883L_I2C_H_ */
