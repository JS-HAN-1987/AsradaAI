# ====================================
# alert_checker.py
# 차량 상태 알림 체크
# ====================================

from typing import Optional, List
from .car_data import CarDataSnapshot


class AlertChecker:
    """차량 상태 알림 체크 클래스"""

    @staticmethod
    def check_sudden_acceleration(current: CarDataSnapshot, previous: CarDataSnapshot) -> Optional[str]:
        """급가속 체크"""
        curr_speed = current.get_speed_value()
        prev_speed = previous.get_speed_value()

        if curr_speed is not None and prev_speed is not None:
            speed_diff = curr_speed - prev_speed
            if speed_diff > 20:
                return f"[급가속 감지] 속도 변화: +{speed_diff:.1f} km/h"
        return None

    @staticmethod
    def check_sudden_braking(current: CarDataSnapshot, previous: CarDataSnapshot) -> Optional[str]:
        """급감속 체크"""
        curr_speed = current.get_speed_value()
        prev_speed = previous.get_speed_value()

        if curr_speed is not None and prev_speed is not None:
            speed_diff = prev_speed - curr_speed
            if speed_diff > 25:
                return f"[급감속 감지] 속도 변화: -{speed_diff:.1f} km/h"
        return None

    @staticmethod
    def check_engine_overheat(snapshot: CarDataSnapshot) -> Optional[str]:
        """엔진 과열 체크"""
        coolant_temp = snapshot.get_coolant_temp_value()
        if coolant_temp and coolant_temp > 105:
            return f"[엔진 과열 경고] 냉각수 온도: {coolant_temp}°C"
        return None

    @staticmethod
    def check_oil_overheat(snapshot: CarDataSnapshot) -> Optional[str]:
        """오일 과열 체크"""
        oil_temp = snapshot.oil_temp.value if snapshot.oil_temp else None
        if oil_temp and oil_temp > 130:
            return f"[오일 과열 경고] 오일 온도: {oil_temp}°C"
        return None

    @staticmethod
    def check_rpm_excessive(snapshot: CarDataSnapshot) -> Optional[str]:
        """과회전 체크"""
        rpm = snapshot.get_rpm_value()
        if rpm and rpm > 6000:
            return f"[과회전 경고] RPM: {rpm}"
        return None

    @staticmethod
    def check_engine_load(snapshot: CarDataSnapshot) -> Optional[str]:
        """엔진 부하 체크"""
        engine_load = snapshot.engine_load.value if snapshot.engine_load else None
        if engine_load and engine_load > 90:
            return f"[엔진 부하 과다] {engine_load}%"
        return None

    @staticmethod
    def check_fuel_level(snapshot: CarDataSnapshot) -> Optional[str]:
        """연료 부족 체크"""
        fuel_level = snapshot.get_fuel_level_value()
        if fuel_level and fuel_level < 15:
            return f"[연료 부족 경고] 연료 잔량: {fuel_level}%"
        return None

    @staticmethod
    def check_fuel_rate(snapshot: CarDataSnapshot) -> Optional[str]:
        """연료 소비율 체크"""
        fuel_rate = snapshot.fuel_rate.value if snapshot.fuel_rate else None
        if fuel_rate and fuel_rate > 15:
            return f"[높은 연료 소비] 소비율: {fuel_rate:.2f} L/h"
        return None

    @staticmethod
    def check_fuel_pressure(snapshot: CarDataSnapshot) -> Optional[str]:
        """연료 압력 체크"""
        fuel_pressure = snapshot.fuel_pressure.value if snapshot.fuel_pressure else None
        if fuel_pressure and (fuel_pressure < 200 or fuel_pressure > 500):
            return f"[연료 압력 이상] {fuel_pressure} kPa"
        return None

    @staticmethod
    def check_dtc(snapshot: CarDataSnapshot) -> List[str]:
        """DTC 체크"""
        alerts = []
        if snapshot.dtc_list:
            for dtc in snapshot.dtc_list:
                alerts.append(f"[고장 코드 감지] {dtc.code}: {dtc.message}")
        return alerts

    @staticmethod
    def check_mil_distance(snapshot: CarDataSnapshot) -> Optional[str]:
        """MIL 점등 주행거리 체크"""
        distance_w_mil = snapshot.distance_w_mil.value if snapshot.distance_w_mil else None
        if distance_w_mil and distance_w_mil > 100:
            return f"[체크엔진 경고] MIL 켜진 상태로 {distance_w_mil} km 주행"
        return None

    @staticmethod
    def check_maf(snapshot: CarDataSnapshot) -> Optional[str]:
        """MAF 센서 체크"""
        maf = snapshot.maf.value if snapshot.maf else None
        if maf and (maf < 2 or maf > 200):
            return f"[공기유량센서 이상] MAF: {maf} g/s"
        return None

    @staticmethod
    def check_fuel_trim(snapshot: CarDataSnapshot) -> List[str]:
        """연료 트림 체크"""
        alerts = []

        short_trim_1 = snapshot.short_fuel_trim_1.value if snapshot.short_fuel_trim_1 else None
        if short_trim_1 and abs(short_trim_1) > 25:
            alerts.append(f"[연료 트림 이상] Bank 1 Short: {short_trim_1}%")

        long_trim_1 = snapshot.long_fuel_trim_1.value if snapshot.long_fuel_trim_1 else None
        if long_trim_1 and abs(long_trim_1) > 25:
            alerts.append(f"[연료 트림 이상] Bank 1 Long: {long_trim_1}%")

        return alerts

    @staticmethod
    def check_catalyst_temp(snapshot: CarDataSnapshot) -> List[str]:
        """촉매 온도 체크"""
        alerts = []

        cat_temp_b1s1 = snapshot.catalyst_temp_b1s1.value if snapshot.catalyst_temp_b1s1 else None
        if cat_temp_b1s1 and cat_temp_b1s1 > 900:
            alerts.append(f"[촉매 과열] Bank 1 Sensor 1: {cat_temp_b1s1}°C")

        cat_temp_b2s1 = snapshot.catalyst_temp_b2s1.value if snapshot.catalyst_temp_b2s1 else None
        if cat_temp_b2s1 and cat_temp_b2s1 > 900:
            alerts.append(f"[촉매 과열] Bank 2 Sensor 1: {cat_temp_b2s1}°C")

        return alerts

    @staticmethod
    def check_egr_error(snapshot: CarDataSnapshot) -> Optional[str]:
        """EGR 에러 체크"""
        egr_error = snapshot.egr_error.value if snapshot.egr_error else None
        if egr_error and abs(egr_error) > 15:
            return f"[EGR 시스템 오차] {egr_error}%"
        return None

    @staticmethod
    def check_throttle(snapshot: CarDataSnapshot) -> Optional[str]:
        """스로틀 체크"""
        throttle_pos = snapshot.throttle_pos.value if snapshot.throttle_pos else None
        if throttle_pos and throttle_pos > 90:
            return f"[과도한 가속] 스로틀 위치: {throttle_pos}%"
        return None

    @staticmethod
    def check_accelerator(snapshot: CarDataSnapshot) -> Optional[str]:
        """가속 페달 체크"""
        accel_pos = snapshot.accelerator_pos_d.value if snapshot.accelerator_pos_d else None
        if accel_pos and accel_pos > 95:
            return f"[급가속 페달] 가속 페달: {accel_pos}%"
        return None

    @staticmethod
    def check_voltage(snapshot: CarDataSnapshot) -> Optional[str]:
        """배터리 전압 체크"""
        voltage = snapshot.control_module_voltage.value if snapshot.control_module_voltage else None
        if voltage and (voltage < 12.0 or voltage > 15.0):
            return f"[배터리 전압 이상] {voltage}V"
        return None

    @staticmethod
    def check_maintenance(snapshot: CarDataSnapshot) -> Optional[str]:
        """정비 주기 체크"""
        distance_since_clear = snapshot.distance_since_dtc_clear.value if snapshot.distance_since_dtc_clear else None
        if distance_since_clear and distance_since_clear > 5000 and snapshot.dtc_list:
            return f"[정비 권장] DTC 초기화 후 {distance_since_clear} km 경과"
        return None

    @staticmethod
    def check_runtime(snapshot: CarDataSnapshot) -> Optional[str]:
        """엔진 가동시간 체크"""
        run_time = snapshot.run_time.value if snapshot.run_time else None
        if run_time and run_time > 36000:
            return f"[장시간 운행] 엔진 가동 시간: {run_time // 3600}시간"
        return None

    @classmethod
    def check_all(cls, current: CarDataSnapshot, previous: Optional[CarDataSnapshot] = None) -> List[str]:
        """모든 알림 체크"""
        alerts = []

        # 1. 즉각적인 위험 신호 (이전 데이터 필요)
        if previous:
            alert = cls.check_sudden_acceleration(current, previous)
            if alert: alerts.append(alert)

            alert = cls.check_sudden_braking(current, previous)
            if alert: alerts.append(alert)

        # 현재 상태만으로 체크 가능한 항목들
        alert = cls.check_engine_overheat(current)
        if alert: alerts.append(alert)

        alert = cls.check_oil_overheat(current)
        if alert: alerts.append(alert)

        alert = cls.check_rpm_excessive(current)
        if alert: alerts.append(alert)

        alert = cls.check_engine_load(current)
        if alert: alerts.append(alert)

        # 2. 연료 및 효율 관련
        alert = cls.check_fuel_level(current)
        if alert: alerts.append(alert)

        alert = cls.check_fuel_rate(current)
        if alert: alerts.append(alert)

        alert = cls.check_fuel_pressure(current)
        if alert: alerts.append(alert)

        # 3. 엔진 성능 및 고장
        alerts.extend(cls.check_dtc(current))

        alert = cls.check_mil_distance(current)
        if alert: alerts.append(alert)

        alert = cls.check_maf(current)
        if alert: alerts.append(alert)

        alerts.extend(cls.check_fuel_trim(current))

        # 4. 배기가스 관련
        alerts.extend(cls.check_catalyst_temp(current))

        alert = cls.check_egr_error(current)
        if alert: alerts.append(alert)

        # 5. 운전 습관 분석
        alert = cls.check_throttle(current)
        if alert: alerts.append(alert)

        alert = cls.check_accelerator(current)
        if alert: alerts.append(alert)

        # 6. 유지보수 알림
        alert = cls.check_voltage(current)
        if alert: alerts.append(alert)

        alert = cls.check_maintenance(current)
        if alert: alerts.append(alert)

        alert = cls.check_runtime(current)
        if alert: alerts.append(alert)

        return alerts