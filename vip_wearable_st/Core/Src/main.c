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

uint8_t rx_buffer[6];       // 라파로부터 받을 6바이트 수신 버퍼
uint8_t system_active_flag = 0; // 0: 대기(Sleep), 1: 구동(Active)
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
    MX_USART6_UART_Init();
    /* USER CODE BEGIN 2 */
    while (DRV2605L_Init(&hi2c2, &Haptic_R))
    {
        printf("drv2605l_R 센서 연결 실패\r\n");
        DRV2605L_Reconnect(&Haptic_R);
        HAL_Delay(1000);
    }
    printf("drv2605l_R 센서 연결 완료\r\n");

    while (DRV2605L_Init(&hi2c3, &Haptic_L))
    {
        printf("drv2605l_L 센서 연결 실패\r\n");
        DRV2605L_Reconnect(&Haptic_L);
        HAL_Delay(1000);
    }
    printf("drv2605l_L 센서 연결 완료\r\n");

    while (EBIMU_Init(&huart1, &Heading))
    {
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

    HAL_UART_Receive_IT(&huart6, rx_buffer, 6);
    /* USER CODE END 2 */

    /* Infinite loop */
    /* USER CODE BEGIN WHILE */
    while (1)
    {
        // 💡 [교정 팩트]: BLE 연결 상태 플래그에 따른 최상위 흐름 분기 통제
        if (system_active_flag == 1)
        {
            // 1. 구동 상태일 때만 백그라운드 DMA 버퍼 데이터에서 오일러 각도 실시간 해독
            EBIMU_Get_Euler_Angle(&Heading);

            // 2. 하이퍼파라미터 주기(HAPTIC_UPDATE_PERIOD = 50ms) 마다 낙상 검사 및 가변 햅틱 제어
            if (HAL_GetTick() - last_haptic_tick >= HAPTIC_UPDATE_PERIOD)
            {
                last_haptic_tick = HAL_GetTick(); // 타임스탬프 갱신

                if (FallDetection_Update(&Heading))
                {
                    // 낙상 감지 비상 상황 시 양쪽 모터 고정 강력 경보 진동 (세기: 50)
                    DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 50);
                } else
                {
                    // 🚀 [연동]: 라파로부터 가로챈 앱의 실제 경로 편차 오차 값에 기반하여
                    // 좌우 모터 실시간 RTP 세기 가변 분기 제어 실행
                    DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, (int16_t) app_angle_error);
                }
            }

            // 3. 라즈베리파이로 100ms 마다 최신 수집된 Yaw 방위각 실시간 송출
            if (HAL_GetTick() - last_log_tick >= 100)
            {
                last_log_tick = HAL_GetTick();

                printf("\r\nEuler | %.2f, %.2f, %.2f\r\n", Heading.roll, Heading.pitch, Heading.yaw);

                uint8_t tx_packet[5];
                tx_packet[0] = 0xAA; // 약속된 규격 헤더 주입
                memcpy(&tx_packet[1], &Heading.yaw, sizeof(float));

                HAL_UART_Transmit(&huart6, tx_packet, 5, 10);
            }
        } else
        {
            // 🛑 [대기동작 팩트]: BLE 미연결 시 센서들한테 값도 안 받고 안 주며 초저전력 대기
            // (CPU 점유를 낮추고 인터럽트 수신 대기 상태 유지)
            HAL_Delay(10);
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
    RCC_OscInitTypeDef RCC_OscInitStruct =
    { 0 };
    RCC_ClkInitTypeDef RCC_ClkInitStruct =
    { 0 };

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
    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
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
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {

    } else if (huart->Instance == USART6) // UART6 포트로부터 6바이트 유입 완료 시
    {
        // 1. 프로토콜 헤더 0xAA 검증 가드
        if (rx_buffer[0] == 0xAA)
        {
            uint8_t cmd_flag = rx_buffer[5]; // 맨 마지막 6번째 바이트(상태 플래그) 추출

            if (cmd_flag == 0x01)
            {
                system_active_flag = 1; // 🚀 앱 연결됨 -> ST 보드 구동 모드 전환
            } else if (cmd_flag == 0x00)
            {
                system_active_flag = 0; // 🛑 앱 연결 끊김 -> ST 보드 대기/초기화 모드 전환

                // 대기 동작 진입 시 안전을 위해 진동 모터 드라이버 출력을 완전히 차단합니다.
                app_angle_error = 0.0f;
                DRV2605L_UpdateHapticFeedback(&Haptic_L, &Haptic_R, 0);
            }

            // 2. 💡 [가이드 연동 추가]: 구동 중일 때, 라파를 거쳐 들어오는
            // 4바이트 실시간 경로 오차(Float) 데이터를 추출하여 내부 제어 변수에 동기화 수용
            if (system_active_flag == 1)
            {
                // 빅엔디안 구조의 패킷 실수 복원 연산 수행 (라파 전송 포맷과 1:1 디코드 매칭)
                uint32_t temp_bits = ((uint32_t) rx_buffer[1] << 24) | ((uint32_t) rx_buffer[2] << 16)
                        | ((uint32_t) rx_buffer[3] << 8) | ((uint32_t) rx_buffer[4]);

                // 비트 재매핑을 통해 순수 float 자료형 변수로 메모리 캐스팅 복원
                memcpy(&app_angle_error, &temp_bits, sizeof(float));
            }
        }

        // 3. 중요: 다음 패킷을 연속적으로 가로채기 위해 수신 인터럽트를 재점화합니다.
        HAL_UART_Receive_IT(&huart6, rx_buffer, 6);
    }
}

int _write(int fd, char *ptr, int len)
{
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
    while (1)
    {
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
