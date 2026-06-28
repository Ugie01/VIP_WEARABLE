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

HAL_StatusTypeDef EBIMU_Write(EBIMU_t *sensor, const char *cmd, uint8_t data)
{
    char tx_buffer[40]; // <커맨드입력값>이 담길 임시 송신 버퍼

    // 1. <커맨드입력값> 형태로 문자열 포맷팅 및 안전한 버퍼 결합
    // 예: cmd가 "srp"이고 value가 10 이면 "<srp10>" 문자열 생성
    int len = snprintf(tx_buffer, sizeof(tx_buffer), "<%s%d>", cmd, data);

    // 2. 에러 가드: 버퍼 크기를 초과했거나 포맷팅 실패 시 전송 거부
    if (len < 0 || len >= (int) sizeof(tx_buffer))
    {
        return HAL_ERROR;
    }

    // 3. 변환된 패킷 버퍼를 UART로 전송 (포맷팅된 문자열의 실제 길이인 len 사용)
    return HAL_UART_Transmit(sensor->huart, (uint8_t*) tx_buffer, strlen(tx_buffer), 1000);
}

/**
 * @brief DRV2605 레지스터 읽기 함수
 */
HAL_StatusTypeDef EBIMU_Read(EBIMU_t *sensor, uint16_t size)
{
    // 수신 모드에 맞는 가변 크기 지정 수신
    return HAL_UART_Receive_DMA(sensor->huart, sensor->rx_Data, size);
}

HAL_StatusTypeDef EBIMU_Init(UART_HandleTypeDef *huart, EBIMU_t *sensor)
{

    // 데이터 초기화
    sensor->huart = huart;  // UART 포트 설정
    sensor->roll = 0.0f;
    sensor->pitch = 0.0f;
    sensor->yaw = 0.0f;
    sensor->head = 0; // 읽기 포인터 초기화
    sensor->SET_OUTPUT_CODE = 2; // 기본 HEX 모드로 가정

    memset(sensor->rx_Data, 0, sizeof(sensor->rx_Data));

    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_Get_Euler_Angle(EBIMU_t *sensor)
{
    // 0. 포인터 자체의 Null 예외 가드 처리
    if (sensor == NULL || sensor->huart == NULL)
    {
        return HAL_ERROR;
    }

    if (sensor->SET_OUTPUT_CODE == 1)
    {
        // 버퍼 내에서 패킷의 시작점인 '*' 문자 검색
        char *pStart = strchr((char*) sensor->rx_Data, '*');
        if (pStart == NULL)
        {
            return HAL_ERROR; // 시작 문자가 없으면 파싱 거부
        }

        float t_roll = 0.0f, t_pitch = 0.0f, t_yaw = 0.0f;
        float t_acc_x = 0.0f, t_acc_y = 0.0f, t_acc_z = 0.0f;
        float t_gyro_x = 0.0f, t_gyro_y = 0.0f, t_gyro_z = 0.0f;

        int parsed_cnt = sscanf(pStart, "*%f,%f,%f,%f,%f,%f,%f,%f,%f", &t_roll, &t_pitch, &t_yaw, &t_gyro_x, &t_gyro_y,
                &t_gyro_z, &t_acc_x, &t_acc_y, &t_acc_z);

        if (parsed_cnt == 9)
        {
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

        return HAL_ERROR; // 9개 인자 파싱 실패 시 명시적 에러 리턴 추가
    } else if (sensor->SET_OUTPUT_CODE == 2)
    {
        // DMA 락 스핀이나 초기화 불량 가드 처리
        if (sensor->huart->hdmarx == NULL)
        {
            return HAL_ERROR;
        }

        // 1. 현재 DMA가 쓰고 있는 하드웨어 위치 계산 (Write Pointer)
        uint16_t dma_counter = __HAL_DMA_GET_COUNTER(sensor->huart->hdmarx);
        uint16_t tail = SIZE - dma_counter;

        // 2. 버퍼에 새로 들어온 데이터의 총 길이 계산
        uint16_t data_len = (tail >= sensor->head) ? (tail - sensor->head) : (SIZE - sensor->head + tail);

        // HEX 모드 패킷 크기인 22바이트보다 적게 쌓였다면 다음 주기에 처리
        if (data_len < 22)
        {
            return HAL_BUSY;
        }

        // 3. 링 버퍼 내부 순회하며 헤더(0x55, 0x55) 매칭 검사
        while (data_len >= 22)
        {
            uint16_t idx1 = sensor->head;
            uint16_t idx2 = (sensor->head + 1) % SIZE;

            if (sensor->rx_Data[idx1] == 0x55 && sensor->rx_Data[idx2] == 0x55)
            {
                EBIMU_Packet_t temp_packet;
                uint8_t *p_packet = (uint8_t*) &temp_packet;

                for (uint16_t i = 0; i < 22; i++)
                {
                    p_packet[i] = sensor->rx_Data[(sensor->head + i) % SIZE];
                }

                // 4. 체크섬 검증 진행
                uint16_t calculated_chk = 0;
                for (uint8_t j = 0; j < 20; j++)
                {
                    calculated_chk += p_packet[j];
                }

                if (calculated_chk == __REV16(temp_packet.checksum))
                {
                    sensor->roll = (float) ((int16_t) __REV16(temp_packet.roll_raw)) / 100.0f;
                    sensor->pitch = (float) ((int16_t) __REV16(temp_packet.pitch_raw)) / 100.0f;
                    sensor->yaw = (float) ((int16_t) __REV16(temp_packet.yaw_raw)) / 100.0f;

                    sensor->gyro_x = (float) ((int16_t) __REV16(temp_packet.gyro_x_raw)) / 10.0f;
                    sensor->gyro_y = (float) ((int16_t) __REV16(temp_packet.gyro_y_raw)) / 10.0f;
                    sensor->gyro_z = (float) ((int16_t) __REV16(temp_packet.gyro_z_raw)) / 10.0f;

                    sensor->acc_x = (float) ((int16_t) __REV16(temp_packet.acc_x_raw)) / 1000.0f;
                    sensor->acc_y = (float) ((int16_t) __REV16(temp_packet.acc_y_raw)) / 1000.0f;
                    sensor->acc_z = (float) ((int16_t) __REV16(temp_packet.acc_z_raw)) / 1000.0f;

                    // 포인터를 패킷 크기만큼 이동 후 정상 리턴
                    sensor->head = (sensor->head + 22) % SIZE;
                    return HAL_OK;
                }
            }

            // 헤더가 아니거나 체크섬이 깨진 무효 데이터인 경우 1바이트 전진 슬라이딩
            sensor->head = (sensor->head + 1) % SIZE;
            data_len--;
        }

        return HAL_ERROR; // 무효 데이터를 다 걸러냈음에도 패킷 완성에 실패하면 에러 리턴
    }

    return HAL_ERROR; // 무효한 SET_OUTPUT_CODE 분기 예외 차단용 리턴 보장
}

HAL_StatusTypeDef EBIMU_OUTPUT_ASCII(EBIMU_t *sensor)
{
    sensor->SET_OUTPUT_CODE = 1;
    HAL_UART_DMAStop(sensor->huart); // 기존 DMA 중지 후 재설정
    sensor->head = 0;
    EBIMU_Write(sensor, "soc", 1);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_OUTPUT_HEX(EBIMU_t *sensor)
{
    sensor->SET_OUTPUT_CODE = 2;
    HAL_UART_DMAStop(sensor->huart);
    sensor->head = 0;
    EBIMU_Write(sensor, "soc", 2);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_FORMAT_EulerAngles(EBIMU_t *sensor)
{
    HAL_UART_DMAStop(sensor->huart);
    EBIMU_Write(sensor, "sof", 1);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_FORMAT_Quaternion(EBIMU_t *sensor)
{
    HAL_UART_DMAStop(sensor->huart);
    EBIMU_Write(sensor, "sof", 2);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_SET_GYRO(EBIMU_t *sensor)
{
    HAL_UART_DMAStop(sensor->huart);
    EBIMU_Write(sensor, "sog", 1);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

HAL_StatusTypeDef EBIMU_RESET_GYRO(EBIMU_t *sensor)
{
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
HAL_StatusTypeDef EBIMU_RESET_ACCELERO(EBIMU_t *sensor, uint8_t value)
{
    HAL_UART_DMAStop(sensor->huart);
    EBIMU_Write(sensor, "soa", value);
    memset(sensor->rx_Data, 0, SIZE);
    return EBIMU_Read(sensor, SIZE);
}

