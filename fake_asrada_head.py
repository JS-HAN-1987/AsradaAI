# fake_asrada_head.py
import threading
import time


class FakeAsradaHead:
    """ESP8266 시뮬레이션 클래스 (asrada_head.py와 동일한 인터페이스)"""

    def __init__(self):
        self.port = None
        self.ip = None
        self.sock = None
        self.hostname = None
        self.recv_thread = None
        self.on_message = None
        self._stop_flag = False
        self._connected = False
        self._connection_lock = threading.Lock()

    def set_config(self, hostname="esp8266-d3c2cf.local", port=1234):
        """
        hostname은 사실상 사용 안함
        """
        self.hostname = hostname
        self.port = port
        print(f"[FakeHead] 시뮬레이션 모드 설정 완료")

    def is_connected(self):
        with self._connection_lock:
            return self._connected

    def _set_connected(self, status):
        with self._connection_lock:
            self._connected = status

    def connect(self, retry_count=3):
        """시뮬레이션 연결"""
        if self.is_connected():
            print("[FakeHead] 이미 연결됨")
            return True

        print("[FakeHead] 시뮬레이션 ESP8266 연결 성공!")
        self._set_connected(True)
        self._stop_flag = False

        # 수신 스레드 시작 (시뮬레이션용)
        self.recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
        self.recv_thread.start()

        return True

    def _recv_worker(self):
        """시뮬레이션 수신 스레드"""
        print("[FakeHead] 시뮬레이션 수신 스레드 시작")
        while not self._stop_flag:
            time.sleep(0.5)
            # 시뮬레이션: 버튼 누름 이벤트 주기적으로 발생 (테스트용)
            # 실제 사용 시에는 주석 처리
            # if self.on_message and time.time() % 10 < 0.1:  # 10초마다
            #     self.on_message("BUTTON_PRESS")

        self._set_connected(False)
        print("[FakeHead] 시뮬레이션 수신 스레드 종료")

    def send_packet(self, cmd, data=b''):
        if not self.is_connected():
            print("[FakeHead] 연결 안됨 → 자동 재연결 중…")
            if not self.connect():
                return False

        try:
            #print(f"[FakeHead] 패킷 전송 시뮬레이션: cmd=0x{cmd:02X}, data={data.hex()}")
            return True
        except Exception as e:
            print(f"[FakeHead] 전송 오류: {e}")
            self._set_connected(False)
            return False

    def close(self):
        self._stop_flag = True
        self._set_connected(False)
        print("[FakeHead] 시뮬레이션 연결 종료")

    # ============================
    #     ESP8266 명령어들 (시뮬레이션)
    # ============================
    def send_led_level(self, level: int):
        """LED 단계 설정 (0~3) - 시뮬레이션"""
        if level < 0 or level > 3:
            print(f"[FakeHead] LED 레벨 범위 초과: {level} (0~3)")
            return False
        # print(f"[FakeHead] LED 레벨 설정: {level}")
        level_byte = bytes([0x06, level])
        return self.send_packet(0x01, level_byte)

    def led_set(self, led_index, on=True):
        """개별 LED 제어 - 시뮬레이션"""
        # print(f"[FakeHead] LED {led_index} {'ON' if on else 'OFF'}")
        data = bytes([led_index, 1 if on else 0])
        return self.send_packet(0x01, data)

    def servo_set(self, servo_index, angle):
        """서보 모터 제어 - 시뮬레이션"""
        angle = max(0, min(angle, 180))
        print(f"[FakeHead] 서보 {servo_index} 각도: {angle}°")
        data = bytes([servo_index, angle])
        return self.send_packet(0x02, data)

    def set_ssid(self, ssid_str):
        """WiFi SSID 설정 - 시뮬레이션"""
        print(f"[FakeHead] SSID 설정: {ssid_str}")
        if len(ssid_str) > 31:
            print(f"[FakeHead] SSID 너무 김 (31자 이내): {len(ssid_str)}")
            return False
        data = bytes([0x01]) + ssid_str.encode("utf-8")
        return self.send_packet(0x03, data)

    def set_password(self, pass_str):
        """WiFi 비밀번호 설정 - 시뮬레이션"""
        print(f"[FakeHead] 비밀번호 설정: {'*' * len(pass_str)}")
        if len(pass_str) > 31:
            print(f"[FakeHead] 비밀번호 너무 김 (31자 이내): {len(pass_str)}")
            return False
        data = bytes([0x02]) + pass_str.encode("utf-8")
        return self.send_packet(0x03, data)

    def reboot_esp(self):
        """ESP8266 재부팅 - 시뮬레이션"""
        print("[FakeHead] ESP8266 재부팅 명령")
        data = bytes([0x03])
        success = self.send_packet(0x03, data)
        if success:
            print("[FakeHead] ESP8266 재부팅 명령 전송됨")
            self.close()
        return success

    def get_info(self):
        """현재 연결 정보 반환 - 시뮬레이션"""
        return {
            "hostname": self.hostname or "fake-esp8266.local",
            "ip": self.ip or "192.168.1.100",
            "port": self.port or 1234,
            "connected": self.is_connected(),
            "simulation": True
        }


# 글로벌 싱글톤
fake_head = FakeAsradaHead()