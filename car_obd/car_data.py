# ====================================
# car_data.py
# 차량 데이터 구조체 및 히스토리 관리
# ====================================

from dataclasses import dataclass, asdict, field
from typing import Optional, List
from threading import Lock
from collections import deque


@dataclass
class BasicSensor:
    """기본 센서 데이터"""
    value: Optional[float] = None
    unit: Optional[str] = None


@dataclass
class DTCInfo:
    """DTC 정보"""
    code: str
    message: str


@dataclass
class CarDataSnapshot:
    """차량 데이터 스냅샷"""
    timestamp: str

    # 기본 정보
    speed: Optional[BasicSensor] = None
    rpm: Optional[BasicSensor] = None
    coolant_temp: Optional[BasicSensor] = None
    fuel_level: Optional[BasicSensor] = None
    throttle_pos: Optional[BasicSensor] = None
    elm_voltage: Optional[BasicSensor] = None

    # 엔진 부하 및 성능
    engine_load: Optional[BasicSensor] = None
    oil_temp: Optional[BasicSensor] = None
    maf: Optional[BasicSensor] = None
    timing_advance: Optional[BasicSensor] = None

    # 연료 시스템
    fuel_rate: Optional[BasicSensor] = None
    fuel_pressure: Optional[BasicSensor] = None
    ethanol_percent: Optional[BasicSensor] = None
    short_fuel_trim_1: Optional[BasicSensor] = None
    long_fuel_trim_1: Optional[BasicSensor] = None
    short_fuel_trim_2: Optional[BasicSensor] = None
    long_fuel_trim_2: Optional[BasicSensor] = None

    # 배기가스 시스템
    catalyst_temp_b1s1: Optional[BasicSensor] = None
    catalyst_temp_b2s1: Optional[BasicSensor] = None
    commanded_egr: Optional[BasicSensor] = None
    egr_error: Optional[BasicSensor] = None
    evap_vapor_pressure: Optional[BasicSensor] = None

    # 운전 습관
    accelerator_pos_d: Optional[BasicSensor] = None

    # 유지보수
    run_time: Optional[BasicSensor] = None
    distance_since_dtc_clear: Optional[BasicSensor] = None
    distance_w_mil: Optional[BasicSensor] = None
    control_module_voltage: Optional[BasicSensor] = None

    # 고장 진단
    dtc_list: List[DTCInfo] = field(default_factory=list)

    def get_speed_value(self) -> Optional[float]:
        """속도 값 추출"""
        return self.speed.value if self.speed else None

    def get_rpm_value(self) -> Optional[float]:
        """RPM 값 추출"""
        return self.rpm.value if self.rpm else None

    def get_coolant_temp_value(self) -> Optional[float]:
        """냉각수 온도 값 추출"""
        return self.coolant_temp.value if self.coolant_temp else None

    def get_fuel_level_value(self) -> Optional[float]:
        """연료 레벨 값 추출"""
        return self.fuel_level.value if self.fuel_level else None

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (JSON 저장용)"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CarDataSnapshot':
        """딕셔너리로부터 객체 생성"""
        # BasicSensor 복원
        for key, value in data.items():
            if isinstance(value, dict) and 'value' in value and key != 'dtc_list':
                data[key] = BasicSensor(**value)

        # DTCInfo 복원
        if 'dtc_list' in data:
            data['dtc_list'] = [DTCInfo(**dtc) for dtc in data['dtc_list']]

        return cls(**data)


class CarDataHistory:
    """차량 데이터 히스토리 관리"""

    def __init__(self, max_size: int = 20):
        """
        Args:
            max_size: 메모리에 보관할 최대 스냅샷 개수 (알람 체크용)
        """
        self.max_size = max_size
        self.history: deque[CarDataSnapshot] = deque(maxlen=max_size)
        self.lock = Lock()

    def add(self, snapshot: CarDataSnapshot):
        """새 스냅샷 추가"""
        with self.lock:
            self.history.append(snapshot)

    def get_latest(self) -> Optional[CarDataSnapshot]:
        """최신 데이터 조회"""
        with self.lock:
            return self.history[-1] if self.history else None

    def get_previous(self, n: int = 1) -> Optional[CarDataSnapshot]:
        """n번째 이전 데이터 조회"""
        with self.lock:
            if len(self.history) > n:
                return self.history[-(n + 1)]
            return None

    def get_all(self) -> List[CarDataSnapshot]:
        """모든 히스토리 조회"""
        with self.lock:
            return list(self.history)

    def get_recent(self, n: int) -> List[CarDataSnapshot]:
        """최근 n개 조회"""
        with self.lock:
            return list(self.history)[-n:] if len(self.history) >= n else list(self.history)

    def clear(self):
        """히스토리 초기화"""
        with self.lock:
            self.history.clear()

    def size(self) -> int:
        """현재 히스토리 크기"""
        with self.lock:
            return len(self.history)