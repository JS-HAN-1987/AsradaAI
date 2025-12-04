# ====================================
# obd_connector.py
# OBD-II 연결 및 데이터 수집
# ====================================

import obd
import time
from datetime import datetime
from typing import Optional
from .car_data import CarDataSnapshot, BasicSensor, DTCInfo

# 수집할 PID 매핑
PID_MAPPING = {
    'speed': obd.commands.SPEED,
    'rpm': obd.commands.RPM,
    'coolant_temp': obd.commands.COOLANT_TEMP,
    'fuel_level': obd.commands.FUEL_LEVEL,
    'throttle_pos': obd.commands.THROTTLE_POS,
    'elm_voltage': obd.commands.ELM_VOLTAGE,
    'engine_load': obd.commands.ENGINE_LOAD,
    'oil_temp': obd.commands.OIL_TEMP,
    'fuel_rate': obd.commands.FUEL_RATE,
    'fuel_pressure': obd.commands.FUEL_PRESSURE,
    'ethanol_percent': obd.commands.ETHANOL_PERCENT,
    'maf': obd.commands.MAF,
    'timing_advance': obd.commands.TIMING_ADVANCE,
    'short_fuel_trim_1': obd.commands.SHORT_FUEL_TRIM_1,
    'long_fuel_trim_1': obd.commands.LONG_FUEL_TRIM_1,
    'short_fuel_trim_2': obd.commands.SHORT_FUEL_TRIM_2,
    'long_fuel_trim_2': obd.commands.LONG_FUEL_TRIM_2,
    'catalyst_temp_b1s1': obd.commands.CATALYST_TEMP_B1S1,
    'catalyst_temp_b2s1': obd.commands.CATALYST_TEMP_B2S1,
    'commanded_egr': obd.commands.COMMANDED_EGR,
    'egr_error': obd.commands.EGR_ERROR,
    'evap_vapor_pressure': obd.commands.EVAP_VAPOR_PRESSURE,
    'accelerator_pos_d': obd.commands.ACCELERATOR_POS_D,
    'run_time': obd.commands.RUN_TIME,
    'distance_since_dtc_clear': obd.commands.DISTANCE_SINCE_DTC_CLEAR,
    'distance_w_mil': obd.commands.DISTANCE_W_MIL,
    'control_module_voltage': obd.commands.CONTROL_MODULE_VOLTAGE,
}


class OBDConnector:
    """OBD-II 연결 및 데이터 수집 클래스"""

    def __init__(self, port: str = "COM4", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.connection: Optional[obd.OBD] = None

    def connect(self) -> bool:
        """OBD-II 연결 시도"""
        try:
            print(f"[INFO] Connecting to OBD-II on {self.port} @ {self.baudrate}...")
            self.connection = obd.OBD(portstr=self.port, baudrate=self.baudrate, fast=False)

            if self.connection.is_connected():
                print("[INFO] OBD-II Connected.")
                return True
            else:
                print("[WARN] OBD not detected.")
                return False

        except Exception as e:
            print(f"[ERROR] OBD connection error: {e}")
            return False

    def is_fake(self) -> bool:
        return False

    def reconnect(self):
        """연결이 끊겼을 때 재연결"""
        if self.connect():
            return

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self.connection is not None and self.connection.is_connected()

    def _sanitize_value(self, value):
        """JSON 직렬화 안전 처리"""
        if value is None:
            return None
        if hasattr(value, "magnitude"):
            return float(value.magnitude)
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value

    def _read_dtc(self) -> list[DTCInfo]:
        """DTC 읽기"""
        try:
            response = self.connection.query(obd.commands.GET_DTCS)

            if response and not response.is_null():
                return [DTCInfo(code=code, message=msg) for code, msg in response.value]
            return []

        except Exception as e:
            print(f"[ERROR] Reading GET_DTCS: {e}")
            return []

    def collect_data(self) -> CarDataSnapshot:
        """OBD에서 데이터 수집하여 CarDataSnapshot 생성"""
        if not self.is_connected():
            raise ConnectionError("OBD not connected")

        snapshot = CarDataSnapshot(timestamp=datetime.now().isoformat())

        # PID 조회
        for field_name, cmd in PID_MAPPING.items():
            try:
                response = self.connection.query(cmd)

                if not response.is_null():
                    value = self._sanitize_value(response.value)
                    unit = str(response.unit) if response.unit else None
                    sensor = BasicSensor(value=value, unit=unit)
                    setattr(snapshot, field_name, sensor)

            except Exception as e:
                # 실패한 센서는 None으로 유지
                pass

        # DTC 조회
        snapshot.dtc_list = self._read_dtc()

        return snapshot

    def disconnect(self):
        """연결 종료"""
        if self.connection:
            try:
                self.connection.close()
                print("[INFO] OBD connection closed.")
            except:
                pass