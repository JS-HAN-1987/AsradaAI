# asrada_head.py
import socket
import threading


class AsradaHead:
    def __init__(self):
        self.port = None
        self.ip = None
        self.sock = None
        self.recv_thread = None
        self.on_message = None  # 🚀 수신 메시지 콜백 (BUTTON_PRESS 등)

        self._stop_flag = False
        self._connected = False  # 🆕 연결 상태 플래그
        self._connection_lock = threading.Lock()  # 🆕 연결 동기화를 위한 락

    def set_config(self, ip, port=1234):
        self.ip = ip
        self.port = port

    # 🆕 연결 상태 확인 메서드
    def is_connected(self):
        """ESP8266과의 연결 상태를 반환"""
        with self._connection_lock:
            return self._connected and self.sock is not None

    # 🆕 연결 상태 설정 메서드
    def _set_connected(self, status):
        """내부용: 연결 상태 업데이트"""
        with self._connection_lock:
            self._connected = status

    # ============================
    #        소켓 연결
    # ============================
    def connect(self):
        """ESP8266과 TCP 소켓 연결 + 수신 스레드 시작"""
        # 이미 연결되어 있으면
        if self.is_connected():
            return
#            self.close()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)  # 🆕 연결 타임아웃 설정
            self.sock.connect((self.ip, self.port))

            self._set_connected(True)
            print(f"[Head] Connected to {self.ip}:{self.port}")

            # 🔥 수신 스레드 시작
            self._stop_flag = False
            self.recv_thread = threading.Thread(
                target=self._recv_worker, daemon=True
            )
            self.recv_thread.start()

            return True

        except Exception as e:
            print(f"[Head] Connection failed: {e}")
            self._set_connected(False)
            if self.sock:
                self.sock.close()
                self.sock = None
            return False

    # ============================
    #      수신 루프(Thread)
    # ============================
    def _recv_worker(self):
        """ESP8266이 보내는 메시지를 모두 수신하는 스레드"""
        while not self._stop_flag:
            try:
                data = self.sock.recv(1024)
                if not data:
                    # 🆕 연결이 끊어진 경우
                    print("[Head] Connection closed by ESP")
                    self._set_connected(False)
                    break

                msg = data.decode(errors="ignore").strip()

                if msg:
                    print(f"[Head] 수신: {msg}")

                    # 🚀 버튼 콜백으로 전달
                    if self.on_message:
                        self.on_message(msg)

            except socket.timeout:
                # 🆕 타임아웃은 정상적으로 계속 진행
                continue
            except Exception as e:
                print(f"[Head] Recv 오류: {e}")
                self._set_connected(False)
                break

    def close(self):
        """소켓 종료"""
        self._stop_flag = True
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        finally:
            self.sock = None
            self._set_connected(False)

    # ============================
    #     패킷 전송 공용 함수
    # ============================
    def send_packet(self, cmd, data=b''):
        """
        패킷 형식:
        AA | CMD | DATA... | BB
        """
        if not self.is_connected():
#            print("[Head] Not connected, cannot send packet")
            return False

        try:
            packet = b'\xAA' + bytes([cmd]) + data + b'\xBB'
            self.sock.send(packet)
            return True
        except Exception as e:
            print(f"[Head] Send 오류: {e}")
            self._set_connected(False)
            return False

    def send_led_level(self, level: int):
        level_byte = bytes([0x06, level])
        return self.send_packet(0x01, level_byte)  # 🆕 반환값 전달

    # ============================
    #     편의 함수들
    # ============================
    def led_set(self, led_index, on=True):
        data = bytes([led_index, 1 if on else 0])
        return self.send_packet(0x01, data)  # 🆕 반환값 전달

    def servo_set(self, servo_index, angle):
        if not self.is_connected():
            print("[Head] Not connected, cannot set servo")
            return False

        angle = max(0, min(angle, 180))
        data = bytes([servo_index, angle])
        return self.send_packet(0x02, data)  # 🆕 반환값 전달

    def set_ssid(self, ssid_str):
        data = bytes([0x01]) + ssid_str.encode("utf-8")
        return self.send_packet(0x03, data)  # 🆕 반환값 전달

    def set_password(self, pass_str):
        data = bytes([0x02]) + pass_str.encode("utf-8")
        return self.send_packet(0x03, data)  # 🆕 반환값 전달


# 글로벌 싱글톤
head = AsradaHead()