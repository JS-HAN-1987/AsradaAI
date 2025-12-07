#!/usr/bin/env python3
# obd_finder.py - OBD-II 포트 자동 검색 및 연결 (RFCOMM만)

import os
import sys
import time
import subprocess
import re
import glob
import serial
from typing import Optional, Tuple, List


class OBDFinder:
    """OBD-II 포트 자동 검색 및 연결 클래스 (RFCOMM만)"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.found_port = None

    def log(self, message: str):
        """로그 출력"""
        if self.verbose:
            print(f"[OBDFinder] {message}")

    def run_command(self, cmd: str, timeout: int = 10) -> Tuple[str, str]:
        """명령어 실행"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return "", "Timeout"
        except Exception as e:
            return "", str(e)

    def is_serial_port_available(self, port: str) -> bool:
        """시리얼 포트 존재 여부 확인"""
        return os.path.exists(port)

    def find_rfcomm_ports(self) -> List[str]:
        """RFCOMM 포트 찾기"""
        ports = glob.glob('/dev/rfcomm*')
        ports.sort()
        return ports

    def test_serial_port(self, port: str) -> bool:
        """시리얼 포트 테스트 (OBD 여부 확인)"""
        if not self.is_serial_port_available(port):
            return False

        try:
            self.log(f"포트 테스트: {port}")
            ser = serial.Serial(
                port=port,
                baudrate=115200,
                timeout=2,
                write_timeout=2
            )

            # ELM327 호환 테스트
            test_commands = [b'ATZ\r', b'ATI\r', b'ATE0\r']

            for cmd in test_commands:
                try:
                    ser.write(cmd)
                    time.sleep(0.5)
                    response = ser.read(ser.in_waiting or 1024)

                    if response:
                        response_str = response.decode('ascii', errors='ignore')
                        # ELM327 응답 확인
                        if 'ELM' in response_str.upper() or 'OK' in response_str.upper():
                            ser.close()
                            self.log(f"  ✓ OBD 응답: {response_str.strip()}")
                            return True
                except:
                    continue

            ser.close()
            return False

        except Exception as e:
            self.log(f"  ✗ 테스트 실패: {e}")
            return False

    def setup_bluetooth(self) -> bool:
        """블루투스 서비스 설정"""
        try:
            # 블루투스 서비스 시작
            self.run_command("sudo systemctl start bluetooth")
            self.run_command("sudo rfkill unblock bluetooth")
            time.sleep(2)
            return True
        except:
            return False

    def find_bluetooth_obd(self) -> Optional[Tuple[str, str]]:
        """블루투스 OBD 어댑터 찾기 (MAC 주소와 이름 반환)"""
        self.log("블루투스 OBD 검색 중...")

        # 블루투스 설정 확인
        if not self.setup_bluetooth():
            self.log("블루투스 서비스 시작 실패")
            return None

        # 블루투스 장치 검색
        stdout, stderr = self.run_command("sudo hcitool scan", timeout=15)

        if not stdout:
            self.log("블루투스 장치 검색 실패")
            return None

        # OBD 장치 찾기
        lines = stdout.strip().split('\n')
        obd_devices = []

        for line in lines[1:]:  # 첫 줄은 헤더
            if not line.strip():
                continue

            # MAC 주소와 이름 추출
            match = re.search(r'((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+(.+)', line)
            if match:
                mac = match.group(1)
                name = match.group(2)

                # OBD 장치 패턴 (더 엄격하게)
                obd_patterns = [
                    r'obd', r'OBD',
                    r'elm', r'ELM',
                    r'327',  # ELM327
                    r'bt.*obd', r'BT.*OBD',
                    r'vgate', r'Vgate',
                    r'car.*link', r'CAR.*LINK'
                ]

                for pattern in obd_patterns:
                    if re.search(pattern, name, re.IGNORECASE):
                        obd_devices.append((mac, name))
                        self.log(f"발견된 OBD: {name} ({mac})")
                        break

        if not obd_devices:
            self.log("블루투스 OBD 어댑터를 찾을 수 없음")
            return None

        # 첫 번째 장치 선택
        mac, name = obd_devices[0]
        self.log(f"선택된 OBD: {name} ({mac})")

        return mac, name

    def pair_bluetooth_device(self, mac: str, name: str) -> Optional[str]:
        """블루투스 장치 페어링 및 RFCOMM 포트 바인딩"""
        self.log(f"{name} 페어링 및 연결 시도...")

        # 페어링 스크립트 생성 (여러 PIN 코드 시도)
        pairing_script = f'''#!/usr/bin/expect -f
set timeout 30

# bluetoothctl 시작
spawn bluetoothctl
expect "# "

# 초기화
send "power on\\r"
expect "# "
send "agent on\\r"
expect "# "
send "default-agent\\r"
expect "# "

# 기존 연결 제거
send "remove {mac}\\r"
expect "# "

# 페어링 시작
send "pair {mac}\\r"
expect {{
    "Enter PIN code:" {{
        # 첫 번째 PIN 시도: 1234
        send "1234\\r"
        exp_continue
    }}
    "Pairing successful" {{
        send "trust {mac}\\r"
        exp_continue
    }}
    "Failed to pair" {{
        # 두 번째 시도: 0000
        send "pair {mac}\\r"
        expect "Enter PIN code:"
        send "0000\\r"
        exp_continue
    }}
    timeout {{
        send "quit\\r"
        exit 1
    }}
}}

# 연결
expect "# "
send "connect {mac}\\r"
expect {{
    "Connection successful" {{
        send "quit\\r"
        exit 0
    }}
    "Failed to connect" {{
        # 재시도
        send "connect {mac}\\r"
        expect "Connection successful" {{
            send "quit\\r"
            exit 0
        }}
        send "quit\\r"
        exit 1
    }}
    timeout {{
        send "quit\\r"
        exit 1
    }}
}}
'''

        # 임시 스크립트 파일 생성
        script_file = "/tmp/obd_pairing.exp"
        with open(script_file, 'w') as f:
            f.write(pairing_script)

        os.chmod(script_file, 0o755)

        # 페어링 실행
        stdout, stderr = self.run_command(f"sudo expect {script_file}", timeout=30)

        if "Connection successful" in stdout:
            self.log("블루투스 페어링 및 연결 성공")

            # RFCOMM 포트 바인딩 (포트 0)
            self.log("RFCOMM 포트 바인딩 (포트 0)...")
            self.run_command("sudo rfcomm release 0 2>/dev/null")
            stdout, stderr = self.run_command(f"sudo rfcomm bind 0 {mac} 1", timeout=10)

            if self.is_serial_port_available("/dev/rfcomm0"):
                self.log("RFCOMM 바인딩 성공: /dev/rfcomm0")
                return "/dev/rfcomm0"

            # 포트 0 실패 시 포트 1 시도
            self.log("RFCOMM 포트 바인딩 (포트 1)...")
            self.run_command("sudo rfcomm release 1 2>/dev/null")
            stdout, stderr = self.run_command(f"sudo rfcomm bind 1 {mac} 1", timeout=10)

            if self.is_serial_port_available("/dev/rfcomm1"):
                self.log("RFCOMM 바인딩 성공: /dev/rfcomm1")
                return "/dev/rfcomm1"

            self.log("RFCOMM 바인딩 실패")
            return None
        else:
            self.log("블루투스 페어링 실패")
            return None

    def connect_existing_rfcomm(self) -> Optional[str]:
        """기존 RFCOMM 포트 연결 시도"""
        self.log("기존 RFCOMM 포트 확인 중...")
        rfcomm_ports = self.find_rfcomm_ports()

        if not rfcomm_ports:
            self.log("RFCOMM 포트 없음")
            return None

        self.log(f"발견된 RFCOMM 포트: {rfcomm_ports}")

        for port in rfcomm_ports:
            if self.test_serial_port(port):
                self.log(f"기존 RFCOMM 포트 연결 성공: {port}")
                return port

        self.log("기존 RFCOMM 포트 중 OBD 응답 없음")
        return None

    def find_obd_port(self) -> Optional[str]:
        """OBD 포트 찾기 (주요 함수)"""
        self.log("OBD 포트 검색 시작 (RFCOMM만)...")

        # 1. 기존 RFCOMM 포트 연결 시도
        existing_port = self.connect_existing_rfcomm()
        if existing_port:
            self.found_port = existing_port
            return self.found_port

        # 2. 새로운 블루투스 OBD 검색 및 연결
        self.log("새로운 블루투스 OBD 검색...")
        device_info = self.find_bluetooth_obd()

        if device_info:
            mac, name = device_info
            new_port = self.pair_bluetooth_device(mac, name)

            if new_port:
                # 연결 테스트
                if self.test_serial_port(new_port):
                    self.found_port = new_port
                    return self.found_port

        # 3. 모든 RFCOMM 포트 재검색 및 테스트
        self.log("모든 RFCOMM 포트 재검색...")
        all_rfcomm_ports = self.find_rfcomm_ports()

        for port in all_rfcomm_ports:
            if self.test_serial_port(port):
                self.found_port = port
                return port

        self.log("OBD 포트를 찾을 수 없음")
        return None

    def test_connection(self, port: str) -> bool:
        """OBD 연결 테스트 (obd 라이브러리 사용)"""
        try:
            import obd
            self.log(f"OBD 라이브러리 연결 테스트: {port}")

            connection = obd.OBD(portstr=port, baudrate=115200, fast=False, timeout=10)

            if connection.is_connected():
                status = connection.status()
                protocol = status.protocol_name if status else "Unknown"
                self.log(f"연결 성공! 프로토콜: {protocol}")
                connection.close()
                return True
            else:
                self.log("연결 실패")
                return False

        except ImportError:
            self.log("obd 라이브러리가 없습니다")
            return False
        except Exception as e:
            self.log(f"연결 테스트 오류: {e}")
            return False

    def get_port_info(self, port: str) -> dict:
        """포트 정보 가져오기"""
        info = {
            'port': port,
            'exists': self.is_serial_port_available(port),
            'is_obd': False,
            'test_response': None
        }

        if info['exists']:
            info['is_obd'] = self.test_serial_port(port)

        return info


def main():
    """메인 함수"""
    print("=" * 50)
    print("OBD-II RFCOMM 포트 자동 검색 도구")
    print("=" * 50)

    finder = OBDFinder(verbose=True)

    print("\n1. RFCOMM 포트 검색 중...")
    port = finder.find_obd_port()

    print("\n" + "=" * 50)

    if port:
        print(f"✅ OBD 포트 발견: {port}")

        # 상세 정보 출력
        info = finder.get_port_info(port)
        print(f"\n포트 정보:")
        print(f"  - 경로: {info['port']}")
        print(f"  - 존재: {'예' if info['exists'] else '아니오'}")
        print(f"  - OBD 응답: {'예' if info['is_obd'] else '아니오'}")

        # 연결 테스트
        print("\n2. OBD 라이브러리 연결 테스트 중...")
        if finder.test_connection(port):
            print("✅ OBD 연결 테스트 성공!")
        else:
            print("⚠️  OBD 라이브러리 연결 실패")
    else:
        print("❌ OBD 포트를 찾을 수 없음")
        print("\n문제 해결 방법:")
        print("1. 블루투스가 켜져 있는지 확인하세요")
        print("2. OBD 어댑터 전원이 켜져 있는지 확인하세요")
        print("3. OBD 어댑터가 페어링 모드인지 확인하세요")
        print("4. sudo 권한으로 실행했는지 확인하세요")

    print("\n" + "=" * 50)

    if port:
        print("사용 방법:")
        print(f"  포트: {port}")
        print(f"  Baudrate: 115200")
        print(f"  Python 코드: obd.OBD(portstr='{port}', baudrate=115200)")

    print("=" * 50)

    return port


if __name__ == "__main__":
    # 직접 실행 시
    try:
        port = main()

        # 결과를 다른 스크립트에서 사용할 수 있도록 출력
        if len(sys.argv) > 1:
            if sys.argv[1] == "--export":
                if port:
                    print(f"\n# 환경변수 설정:")
                    print(f"export OBD_PORT='{port}'")
                else:
                    print("\n# OBD 포트를 찾을 수 없음")
            elif sys.argv[1] == "--port-only":
                if port:
                    print(port)
                else:
                    print("")
            elif sys.argv[1] == "--help":
                print("\n사용법:")
                print("  sudo python3 obd_finder.py           # 일반 실행")
                print("  sudo python3 obd_finder.py --export  # 환경변수 출력")
                print("  sudo python3 obd_finder.py --port-only  # 포트만 출력")
                print("  sudo python3 obd_finder.py --help    # 도움말")

    except KeyboardInterrupt:
        print("\n\n❌ 사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 오류 발생: {e}")
        sys.exit(1)