/* USER CODE BEGIN Header */
/**
 ******************************************************************************
 * @file           : main.c
 * @brief          : Main program body
 ******************************************************************************
 * @attention
 *
 * Copyright (c) 2026 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "dma.h"
#include "i2c.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "drv2605_i2c.h"
#include "ebimu_uart.h"
#include "fall_detection.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define RX_DATA_SIZE 7

#define HAPTIC_ROTATE_PERIOD    250  // 회전 햅틱 제어 주기
#define HAPTIC_UPDATE_PERIOD    50   // 직진 햅틱 제어 주기
#define SERIAL_PERIOD    100  // 시리얼 전송 주기
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

DRV2605L_t Haptic_L;
DRV2605L_t Haptic_R;
EBIMU_t Heading;

uint8_t rx_buffer[RX_DATA_SIZE];               // 라즈베리파이로부터 받을 7바이트 수신 버퍼
uint8_t system_active_flag = 0;     // 0: 대기, 1: 구동
uint8_t feedback_flag = 0;          // 0: 일반, 1: 회피
uint32_t last_uart_tx_tick = 0;

float app_angle_error = 0.0f;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
 * @brief  The application entry point.
 * @retval int
 */
int main(void) {

	/* USER CODE BEGIN 1 */

	/* USER CODE END 1 */

	/* MCU Configuration--------------------------------------------------------*/

	/* Reset of all peripherals, Initializes the Flash interface and the Systick. */
	HAL_Init();

	/* USER CODE BEGIN Init */

	/* USER CODE END Init */

	/* Configure the system clock */
	SystemClock_Config();

	/* USER CODE BEGIN SysInit */

	/* USER CODE END SysInit */

	/* Initialize all configured peripherals */
	MX_GPIO_Init();
	MX_DMA_Init();
	MX_USART2_UART_Init();
	MX_I2C3_Init();
	MX_I2C2_Init();
	MX_USART1_UART_Init();
	MX_USART6_UART_Init();
	/* USER CODE BEGIN 2 */

	HAL_Delay(200); // 안정화 대기
	while (DRV2605L_Init(&hi2c2, &Haptic_R)) {
		printf("drv2605l_R 센서 연결 실패\r\n");
		DRV2605L_Reconnect(&Haptic_R);
		HAL_Delay(1000);
	}
	printf("drv2605l_R 센서 연결 완료\r\n");

	HAL_Delay(200); // 센서 안정화 대기
	while (DRV2605L_Init(&hi2c3, &Haptic_L)) {
		printf("drv2605l_L 센서 연결 실패\r\n");
		DRV2605L_Reconnect(&Haptic_L);
		HAL_Delay(1000);
	}
	printf("drv2605l_L 센서 연결 완료\r\n");

	HAL_Delay(200); // 센서 안정화 대기
	while (EBIMU_Init(&huart1, &Heading)) {
		printf("EBIMU 센서 연결 실패\r\n");
		HAL_Delay(1000);
	}
	printf("EBIMU 센서 연결 완료\r\n");
	HAL_Delay(200); // 센서 안정화 대기.

	EBIMU_FORMAT_EulerAngles(&Heading);
	HAL_Delay(200); // 센서 안정화 대기

	EBIMU_SET_GYRO(&Heading);
	HAL_Delay(200); // 센서 안정화 대기

	EBIMU_RESET_ACCELERO(&Heading, 1);
	HAL_Delay(200); // 센서 안정화 대기

	EBIMU_OUTPUT_HEX(&Heading);
//	EBIMU_OUTPUT_ASCII(&Heading);
	HAL_Delay(200); // 센서 안정화 대기

	FallDetection_Init();

	uint32_t last_haptic_tick = HAL_GetTick();
	uint32_t last_log_tick = HAL_GetTick();
	uint32_t last_feedback_toggle_tick = HAL_GetTick();

	uint8_t feedback_output_state = 0; // 1: 진동 ON, 0: 진동 OFF
	HAL_UART_Receive_IT(&huart6, rx_buffer, RX_DATA_SIZE);
	/* USER CODE END 2 */

	/* Infinite loop */
	/* USER CODE BEGIN WHILE */
	while (1) {
		// BLE 연결 상태 플래그에 따른 최상위 흐름 분기 통제
		if (system_active_flag == 1) {
			// 구동 상태일 때만 백그라운드 DMA 버퍼 데이터에서 오일러 각도 실시간 해독
			EBIMU_Get_Euler_Angle(&Heading);

			if (feedback_flag == 1) {
				// 500ms 간격으로 ON / OFF 토글 제어
				if (HAL_GetTick() - last_feedback_toggle_tick >= HAPTIC_ROTATE_PERIOD) {
					last_feedback_toggle_tick = HAL_GetTick();
					feedback_output_state = !feedback_output_state; // 상태 반전 (1 -> 0 -> 1 ...)
				}

				// 토글 상태 및 HAPTIC_UPDATE_PERIOD 주기에 맞춰 출력 반영
				if (HAL_GetTick() - last_haptic_tick >= HAPTIC_UPDATE_PERIOD) {
					last_haptic_tick = HAL_GetTick();

					if (feedback_output_state == 1) {
						// 진동 ON 구간: 받은 값에 따라 세기 가변 제어
						DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, (int16_t) app_angle_error);
					} else {
						// 진동 OFF 구간: 세기를 0으로 만들어 정지
						DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 0);
					}
				}
			} else if (feedback_flag == 0) {
				// 주기마다 낙상 검사 및 가변 햅틱 제어
				if (HAL_GetTick() - last_haptic_tick >= HAPTIC_UPDATE_PERIOD) {
					last_haptic_tick = HAL_GetTick();

					// 라파로부터 가로챈 앱의 실제 경로 편차 오차 값에 기반하여 좌우 모터 실시간 RTP 세기 가변 분기 제어 실행
					DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, (int16_t) app_angle_error);
				}
			}

			// 낙상 감지 비상 상황 시 양쪽 모터 고정 강력 경보 진동
			if (FallDetection_Update(&Heading))
				DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 50);

			// 라즈베리파이로 100ms 마다 최신 수집된 Yaw 방위각 실시간 송출
			if (HAL_GetTick() - last_log_tick >= 100) {
				last_log_tick = HAL_GetTick();

				uint8_t tx_packet[9];
				tx_packet[0] = 0xAA;
				memcpy(&tx_packet[1], &Heading.yaw, sizeof(float));
				memcpy(&tx_packet[5], &Heading.pitch, sizeof(float));

				HAL_UART_Transmit(&huart6, tx_packet, sizeof(tx_packet), 10);
			}

		} else {
//			DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 0);

			// BLE 미연결 시 센서들한테 값도 안 받고 안 주며 초저전력 대기
			HAL_Delay(500);
		}
		/* USER CODE END WHILE */

		/* USER CODE BEGIN 3 */
	}
	/* USER CODE END 3 */
}

/**
 * @brief System Clock Configuration
 * @retval None
 */
void SystemClock_Config(void) {
	RCC_OscInitTypeDef RCC_OscInitStruct = { 0 };
	RCC_ClkInitTypeDef RCC_ClkInitStruct = { 0 };

	/** Configure the main internal regulator output voltage
	 */
	__HAL_RCC_PWR_CLK_ENABLE();
	__HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

	/** Initializes the RCC Oscillators according to the specified parameters
	 * in the RCC_OscInitTypeDef structure.
	 */
	RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
	RCC_OscInitStruct.HSIState = RCC_HSI_ON;
	RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
	RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
	RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
	RCC_OscInitStruct.PLL.PLLM = 16;
	RCC_OscInitStruct.PLL.PLLN = 336;
	RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
	RCC_OscInitStruct.PLL.PLLQ = 4;
	if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
		Error_Handler();
	}

	/** Initializes the CPU, AHB and APB buses clocks
	 */
	RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
	RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
	RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
	RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
	RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

	if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
		Error_Handler();
	}
}

/* USER CODE BEGIN 4 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
	if (huart->Instance == USART1) {

	} else if (huart->Instance == USART6) {
		// 프로토콜 헤더 0xAA 검증 가드
		if (rx_buffer[0] == 0xAA) {
			uint8_t cmd_flag = rx_buffer[5]; // 6번째 바이트(상태 플래그)
			uint8_t fb_flag = rx_buffer[6]; // 7번째 바이트(모드 플래그)
			if (cmd_flag == 0x01) {
				system_active_flag = 1; // ST 보드 구동 모드 전환
			} else if (cmd_flag == 0x00) {
				system_active_flag = 0; // ST 보드 대기/초기화 모드 전환

				// 대기 동작 진입 시 안전을 위해 진동 모터 드라이버 출력을 완전히 차단
				app_angle_error = 0.0f;
				DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 0);
			}
			if (fb_flag == 0x00)
				feedback_flag = 0;
			else if (fb_flag == 0x01)
				feedback_flag = 1;

			// 구동 중일 때, 라파를 거쳐 들어오는 4바이트 실시간 경로 오차(Float) 데이터를 추출하여 내부 제어 변수에 동기화 수용
			if (system_active_flag == 1) {
				// 빅엔디안 구조의 패킷 실수 복원 연산 수행 (라파 전송 포맷과 1:1 디코드 매칭)
				uint32_t temp_bits = ((uint32_t) rx_buffer[1] << 24) | ((uint32_t) rx_buffer[2] << 16) | ((uint32_t) rx_buffer[3] << 8) | ((uint32_t) rx_buffer[4]);

				// 비트 재매핑을 통해 순수 float 자료형 변수로 메모리 캐스팅 복원
				memcpy(&app_angle_error, &temp_bits, sizeof(float));
			}
		}
		HAL_UART_Receive_IT(&huart6, rx_buffer, RX_DATA_SIZE);
	}
}

int _write(int fd, char *ptr, int len) {
	HAL_UART_Transmit(&huart2, (uint8_t*) ptr, len, HAL_MAX_DELAY);
	return len;
}
/* USER CODE END 4 */

/**
 * @brief  This function is executed in case of error occurrence.
 * @retval None
 */
void Error_Handler(void) {
	/* USER CODE BEGIN Error_Handler_Debug */
	/* User can add his own implementation to report the HAL error return state */
	__disable_irq();
	while (1) {
	}
	/* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
