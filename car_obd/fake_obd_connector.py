# car_obd/fake_obd_connector.py
import random
import time
from datetime import datetime
from typing import Optional, List
from .car_data import CarDataSnapshot, BasicSensor, DTCInfo


class FakeOBDConnector:
    """
    실제 OBDConnector와 완전히 호환되는 가상 OBD 커넥터
    alert_checker 기준에 맞춰 경고가 발생하지 않는 데이터 생성
    """

    def __init__(self, port: str = "COM4", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.connection = FakeConnection()
        self.base_time = time.time()
        self.speed_trend = 0
        self.driving_cycle = 0

        # 경고 기준에 맞춘 안전한 데이터 범위
        self.safe_ranges = {
            # 급가속/급감속 방지 (속도 변화량 제한)
            'speed_range': (0, 80),  # km/h
            'speed_change_max': 15,  # 한번에 최대 15km/h 변화

            # 엔진 과열 방지
            'coolant_temp': (70, 95),  # 105도 미만
            'oil_temp': (75, 115),  # 130도 미만

            # RPM 과회전 방지
            'rpm_range': (800, 4500),  # 6000미만

            # 엔진 부하
            'engine_load': (20, 80),  # 90% 미만

            # 연료 관련
            'fuel_level': (25, 85),  # 15% 이상
            'fuel_rate': (2, 10),  # 15 L/h 미만
            'fuel_pressure': (250, 450),  # 200-500 사이

            # MAF 센서
            'maf': (3, 15),  # 2-200 사이

            # 연료 트림
            'short_fuel_trim': (-15, 15),  # 25% 미만
            'long_fuel_trim': (-10, 10),  # 25% 미만

            # 촉매 온도
            'catalyst_temp': (350, 750),  # 900도 미만

            # EGR 에러
            'egr_error': (-8, 8),  # 15% 미만

            # 스로틀/가속 페달
            'throttle_pos': (10, 80),  # 90% 미만
            'accelerator_pos': (10, 85),  # 95% 미만

            # 배터리 전압
            'voltage': (12.3, 14.7),  # 12-15 사이

            # 주행 거리/시간
            'distance_since_clear': (200, 3000),  # 5000km 미만
            'distance_w_mil': (0, 80),  # 100km 미만
            'run_time': (600, 18000),  # 36000초 미만
        }

        # DTC (드물게 발생하도록)
        self.dtc_list = [
        ]

    def connect(self) -> bool:
        """OBD-II 연결 시도 (가상)"""
        try:
            print(f"[FAKE] Connecting to OBD-II on {self.port} @ {self.baudrate}...")
            time.sleep(1)
            print("[FAKE] OBD-II Connected.")
            return True
        except Exception as e:
            print(f"[FAKE] OBD connection error: {e}")
            return False

    def is_fake(self):
        return True

    def reconnect(self):
        """연결이 끊겼을 때 재연결 (가상)"""
        print("[FAKE] Reconnecting to OBD...")
        return self.connect()

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return True

    def _sanitize_value(self, value):
        """JSON 직렬화 안전 처리"""
        if value is None:
            return None
        if hasattr(value, "magnitude"):
            return float(value.magnitude)
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value

    def _read_dtc(self) -> List[DTCInfo]:
        """DTC 읽기 (가상) - 10% 확률로 DTC 생성 또는 반환"""
        try:
            # 10% 확률로 DTC 발생
#            if random.random() < 0.1:
#                generated = [
#                    DTCInfo(code="P0300", message="Random/Multiple Cylinder Misfire Detected")
#                ]
#                return generated
            return []

        except Exception as e:
            print(f"[FAKE] Reading DTCs: {e}")
            return []

    def _simulate_realistic_driving(self) -> dict:
        """현실적인 운전 패턴 시뮬레이션"""
        self.driving_cycle += 0.03
        cycle_value = self.driving_cycle % 24  # 24단계 주기

        # 운전 패턴에 따른 안전한 값 생성
        if cycle_value < 6:  # 정차/저속 (0-6)
            return {
                'speed': random.uniform(0, 15),
                'rpm': random.uniform(800, 1200),
                'engine_load': random.uniform(15, 25),
                'throttle': random.uniform(5, 20),
                'accelerator': random.uniform(5, 25)
            }
        elif cycle_value < 12:  # 도심 주행 (6-12)
            return {
                'speed': random.uniform(20, 50),
                'rpm': random.uniform(1500, 2500),
                'engine_load': random.uniform(30, 50),
                'throttle': random.uniform(20, 40),
                'accelerator': random.uniform(25, 50)
            }
        elif cycle_value < 18:  # 고속도로 주행 (12-18)
            return {
                'speed': random.uniform(60, 85),
                'rpm': random.uniform(2000, 3200),
                'engine_load': random.uniform(40, 65),
                'throttle': random.uniform(30, 60),
                'accelerator': random.uniform(40, 70)
            }
        else:  # 감속/정차 (18-24)
            return {
                'speed': random.uniform(10, 40),
                'rpm': random.uniform(1200, 2000),
                'engine_load': random.uniform(20, 40),
                'throttle': random.uniform(10, 30),
                'accelerator': random.uniform(15, 40)
            }

    def collect_data(self) -> CarDataSnapshot:
        """안전한 범위 내에서 데이터 생성"""
        if not self.is_connected():
            raise ConnectionError("OBD not connected")

        driving = self._simulate_realistic_driving()

        snapshot = CarDataSnapshot(timestamp=datetime.now().isoformat())

        # 안전한 범위 내에서 데이터 생성
        snapshot.speed = BasicSensor(
            value=driving['speed'],
            unit="km/h"
        )

        snapshot.rpm = BasicSensor(
            value=driving['rpm'],
            unit="rpm"
        )

        snapshot.coolant_temp = BasicSensor(
            value=random.uniform(*self.safe_ranges['coolant_temp']),
            unit="°C"
        )

        snapshot.fuel_level = BasicSensor(
            value=random.uniform(*self.safe_ranges['fuel_level']),
            unit="%"
        )

        snapshot.throttle_pos = BasicSensor(
            value=driving['throttle'],
            unit="%"
        )

        snapshot.elm_voltage = BasicSensor(
            value=random.uniform(*self.safe_ranges['voltage']),
            unit="V"
        )

        snapshot.engine_load = BasicSensor(
            value=driving['engine_load'],
            unit="%"
        )

        snapshot.oil_temp = BasicSensor(
            value=random.uniform(*self.safe_ranges['oil_temp']),
            unit="°C"
        )

        snapshot.maf = BasicSensor(
            value=random.uniform(*self.safe_ranges['maf']),
            unit="g/s"
        )

        snapshot.timing_advance = BasicSensor(
            value=random.uniform(-3, 15),
            unit="°"
        )

        snapshot.fuel_rate = BasicSensor(
            value=random.uniform(*self.safe_ranges['fuel_rate']),
            unit="L/h"
        )

        snapshot.fuel_pressure = BasicSensor(
            value=random.uniform(*self.safe_ranges['fuel_pressure']),
            unit="kPa"
        )

        snapshot.ethanol_percent = BasicSensor(
            value=random.uniform(0, 5),
            unit="%"
        )

        # 연료 트림 - 안전한 범위 내
        snapshot.short_fuel_trim_1 = BasicSensor(
            value=random.uniform(*self.safe_ranges['short_fuel_trim']),
            unit="%"
        )

        snapshot.long_fuel_trim_1 = BasicSensor(
            value=random.uniform(*self.safe_ranges['long_fuel_trim']),
            unit="%"
        )

        snapshot.short_fuel_trim_2 = BasicSensor(
            value=random.uniform(*self.safe_ranges['short_fuel_trim']),
            unit="%"
        )

        snapshot.long_fuel_trim_2 = BasicSensor(
            value=random.uniform(*self.safe_ranges['long_fuel_trim']),
            unit="%"
        )

        # 촉매 온도 - 안전한 범위 내
        snapshot.catalyst_temp_b1s1 = BasicSensor(
            value=random.uniform(*self.safe_ranges['catalyst_temp']),
            unit="°C"
        )

        snapshot.catalyst_temp_b2s1 = BasicSensor(
            value=random.uniform(*self.safe_ranges['catalyst_temp']),
            unit="°C"
        )

        snapshot.commanded_egr = BasicSensor(
            value=random.uniform(5, 40),
            unit="%"
        )

        snapshot.egr_error = BasicSensor(
            value=random.uniform(*self.safe_ranges['egr_error']),
            unit="%"
        )

        snapshot.evap_vapor_pressure = BasicSensor(
            value=random.uniform(-0.5, 0.5),
            unit="Pa"
        )

        snapshot.accelerator_pos_d = BasicSensor(
            value=driving['accelerator'],
            unit="%"
        )

        snapshot.run_time = BasicSensor(
            value=random.uniform(*self.safe_ranges['run_time']),
            unit="s"
        )

        snapshot.distance_since_dtc_clear = BasicSensor(
            value=random.uniform(*self.safe_ranges['distance_since_clear']),
            unit="km"
        )

        snapshot.distance_w_mil = BasicSensor(
            value=random.uniform(*self.safe_ranges['distance_w_mil']),
            unit="km"
        )

        snapshot.control_module_voltage = BasicSensor(
            value=random.uniform(*self.safe_ranges['voltage']),
            unit="V"
        )

        # DTC 조회
        snapshot.dtc_list = self._read_dtc()

        return snapshot

    def disconnect(self):
        """연결 종료 (가상)"""
        print("[FAKE] OBD connection closed.")


class FakeConnection:
    """가상 연결 객체"""

    def __init__(self):
        self.is_connected_val = True

    def is_connected(self):
        return self.is_connected_val

    def close(self):
        self.is_connected_val = False


# 테스트용 함수: 가상 데이터로 히스토리 채우기
def create_safe_history(size: int = 20) -> List[CarDataSnapshot]:
    """경고 없는 안전한 데이터로 히스토리 생성"""
    connector = FakeOBDConnector()
    connector.connect()

    history = []
    for i in range(size):
        snapshot = connector.collect_data()
        history.append(snapshot)
        time.sleep(0.1)

    connector.disconnect()
    return history

