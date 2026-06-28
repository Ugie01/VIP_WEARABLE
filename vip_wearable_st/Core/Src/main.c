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

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
DRV2605L_t Haptic_L;
DRV2605L_t Haptic_R;
EBIMU_t Heading;

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
int main(void)
{

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
  /* USER CODE BEGIN 2 */
	while (DRV2605L_Init(&hi2c2, &Haptic_R)) {
		printf("drv2605l_R 센서 연결 실패\r\n");
		DRV2605L_Reconnect(&Haptic_R);
		HAL_Delay(1000);
	}
	printf("drv2605l_R 센서 연결 완료\r\n");

	while (DRV2605L_Init(&hi2c3, &Haptic_L)) {
		printf("drv2605l_L 센서 연결 실패\r\n");
		DRV2605L_Reconnect(&Haptic_L);
		HAL_Delay(1000);
	}
	printf("drv2605l_L 센서 연결 완료\r\n");

	while (EBIMU_Init(&huart1, &Heading)) {
		printf("EBIMU 센서 연결 실패\r\n");
		HAL_Delay(1000);
	}
	printf("EBIMU 센서 연결 완료\r\n");
	HAL_Delay(1000); // 센서 안정화 대기.

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
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
	while (1) {
		// 파싱 함수는 딜레이 없이 상시 호출하여 백그라운드 DMA 버퍼 데이터를 최신화함
		HAL_StatusTypeDef imu_status = EBIMU_Get_Euler_Angle(&Heading);

		// 하이퍼파라미터 주기(HAPTIC_UPDATE_PERIOD = 50ms) 마다 햅틱 피드백 연동
		if (HAL_GetTick() - last_haptic_tick >= HAPTIC_UPDATE_PERIOD) {
			last_haptic_tick = HAL_GetTick(); // 타임스탬프 갱신
			if (imu_status == HAL_OK) {
				if (FallDetection_Update(&Heading)) {
					DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 30);
				} else {
					// 정상 파싱된 Yaw 데이터를 제어 입력 값으로 전달
					int16_t current_yaw = (int16_t) Heading.yaw;
					DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, current_yaw);

				}
			}

		}

		// 디버깅 로그 출력 주기는 햅틱 주기와 분리하여 느리게 설정 (예: 500ms)
		// 콘솔창이 너무 빨리 내려가 가상 포트(UART2)가 크래시 나는 것을 방지
		if (HAL_GetTick() - last_log_tick >= 10) {
			last_log_tick = HAL_GetTick();

			if (imu_status == HAL_OK) {
				printf("\r\nEuler | %.2f, %.2f, %.2f\r\n", Heading.roll, Heading.pitch, Heading.yaw);

			}

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
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

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
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
	if (huart->Instance == USART1) {

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
void Error_Handler(void)
{
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
