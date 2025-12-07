# asrada_head.py
import socket
import threading
import time
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener


# ============================
#   mDNS 스캐너 (asrada용)
# ============================

class AsradaMDNSListener(ServiceListener):
    def __init__(self):
        self.found = None

    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if info:
            ip = ".".join(map(str, info.addresses[0]))
            port = info.port
            self.found = (ip, port)


def mdns_find_asrada(timeout=2.0):
    """
    Zeroconf 기반 _asrada._tcp.local. 서비스 IP/Port 찾기
    """
    zeroconf = Zeroconf()
    listener = AsradaMDNSListener()

    browser = ServiceBrowser(
        zeroconf,
        "_asrada._tcp.local.",
        listener
    )

    start = time.time()
    while time.time() - start < timeout:
        if listener.found:
            zeroconf.close()
            return listener.found
        time.sleep(0.1)

    zeroconf.close()
    return None


# ============================
#         AsradaHead
# ============================

class AsradaHead:
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
        hostname은 사실상 사용 안함(뒤에서 mDNS로 자동 탐색)
        """
        self.hostname = hostname
        self.port = port
        print(f"[Head] 설정 완료: mDNS로 '_asrada._tcp.local.'")

    def is_connected(self):
        with self._connection_lock:
            return self._connected and self.sock is not None

    def _set_connected(self, status):
        with self._connection_lock:
            self._connected = status

    # ============================
    #           연결
    # ============================
    def connect(self, retry_count=3):
        """mDNS 기반 자동 IP 탐색 + TCP 연결"""
        if self.is_connected():
            print("[Head] 이미 연결됨")
            return True

        for attempt in range(retry_count):
            print(f"[mDNS] ESP8266(_asrada._tcp.local.) 검색 {attempt+1}/{retry_count}…")

            result = mdns_find_asrada(timeout=2.0)

            if result:
                self.ip, self.port = result
                print(f"[mDNS] 발견됨 → {self.ip}:{self.port}")
            else:
                print("[mDNS] 발견 실패")
                if attempt < retry_count - 1:
                    time.sleep(1)
                continue

            # TCP 연결
            try:
                print(f"[TCP] 연결 시도: {self.ip}:{self.port}")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5)
                self.sock.connect((self.ip, self.port))

                # 연결 후 타임아웃 제거 (블로킹 모드)
                self.sock.settimeout(None)  # ← 이 줄 추가!
                self._set_connected(True)

                print("[Head] 연결 성공!")

                self._stop_flag = False
                self.recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
                self.recv_thread.start()

                return True

            except Exception as e:
                print(f"[TCP] 연결 실패: {e}")
                if self.sock:
                    self.sock.close()
                self.sock = None

        print("[Head] ❌ 최종 연결 실패")
        return False


    # ============================
    #         수신 스레드
    # ============================
    def _recv_worker(self):
        print("[Head] 수신 스레드 시작")
        while not self._stop_flag:
            try:
                data = self.sock.recv(1024)
                if not data:
                    continue
                msg = data.decode().strip()
                print(f"[Head] 수신: {msg}")
                if self.on_message:
                    self.on_message(msg)
            except Exception as e:
                print(f"[Head] 수신 오류: {e}")


        self._set_connected(False)
        print("[Head] 수신 스레드 종료")

    # ============================
    #         전송
    # ============================
    def send_packet(self, cmd, data=b''):
        if not self.is_connected():
            print("[Head] 연결 안됨 → 자동 재연결 중…")
            if not self.connect():
                return False

        try:
            packet = b'\xAA' + bytes([cmd]) + data + b'\xBB'
            self.sock.send(packet)
            return True
        except Exception as e:
            print(f"[Head] 전송 오류: {e}")
            self._set_connected(False)
            return False

    def close(self):
        self._stop_flag = True
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None
        self._set_connected(False)

    # ============================
    #     ESP8266 명령어들
    # ============================
    def send_led_level(self, level: int):
        """LED 단계 설정 (0~3)"""
        if level < 0 or level > 3:
            print(f"[Head] LED 레벨 범위 초과: {level} (0~3)")
            return False
        level_byte = bytes([0x06, level])
        return self.send_packet(0x01, level_byte)

    def led_set(self, led_index, on=True):
        """개별 LED 제어"""
#        if led_index < 1 or led_index > 6:
#            print(f"[Head] LED 인덱스 범위 초과: {led_index} (1~6)")
#            return False
        data = bytes([led_index, 1 if on else 0])
        return self.send_packet(0x01, data)

    def servo_set(self, servo_index, angle):
        """서보 모터 제어"""
#        if servo_index < 1 or servo_index > 2:
#            print(f"[Head] 서보 인덱스 범위 초과: {servo_index} (1~2)")
#            return False
        
        angle = max(0, min(angle, 180))
        data = bytes([servo_index, angle])
        return self.send_packet(0x02, data)

    def set_ssid(self, ssid_str):
        """WiFi SSID 설정"""
        if len(ssid_str) > 31:
            print(f"[Head] SSID 너무 김 (31자 이내): {len(ssid_str)}")
            return False
        data = bytes([0x01]) + ssid_str.encode("utf-8")
        return self.send_packet(0x03, data)

    def set_password(self, pass_str):
        """WiFi 비밀번호 설정"""
        if len(pass_str) > 31:
            print(f"[Head] 비밀번호 너무 김 (31자 이내): {len(pass_str)}")
            return False
        data = bytes([0x02]) + pass_str.encode("utf-8")
        return self.send_packet(0x03, data)

    def reboot_esp(self):
        """ESP8266 재부팅"""
        data = bytes([0x03])
        success = self.send_packet(0x03, data)
        if success:
            print("[Head] ESP8266 재부팅 명령 전송됨")
            self.close()
        return success

    def get_info(self):
        """현재 연결 정보 반환"""
        return {
            "hostname": self.hostname,
            "ip": self.ip,
            "port": self.port,
            "connected": self.is_connected()
        }


# 글로벌 싱글톤
head = AsradaHead()

