from zeroconf import Zeroconf, ServiceBrowser
import time
import socket


SCAN_TIME = 5


class ServiceTypeListener:
    def __init__(self):
        self.service_types = []

    def add_service(self, zeroconf, type, name):
        # 서비스 타입 목록을 저장
        print(f"[SERVICE TYPE FOUND] {name}")
        self.service_types.append(name)


class ServiceInstanceListener:
    def __init__(self, service_type):
        self.service_type = service_type

    def add_service(self, zeroconf, type, name):
        print(f"[INSTANCE FOUND] {name} (type: {type})")

        info = zeroconf.get_service_info(type, name)
        if info:
            if info.addresses:
                for addr in info.addresses:
                    ip = socket.inet_ntoa(addr)
                    print(f"  -> IP: {ip}")
            print(f"  Server: {info.server}")
            print(f"  Port:   {info.port}")
            print(f"  Props:  {info.properties}")
        else:
            print("  (No info returned)")

        print()


def full_mdns_scan():
    zeroconf = Zeroconf()

    print("[1] 서비스 타입 목록 스캔 중...")
    type_listener = ServiceTypeListener()
    ServiceBrowser(zeroconf, "_services._dns-sd._udp.local.", type_listener)
    time.sleep(SCAN_TIME)

    # 중복 제거
    service_types = list(set(type_listener.service_types))

    print("\n[2] 각 서비스 타입의 인스턴스 스캔 시작…\n")
    for service_type in service_types:
        print(f"=== 스캔: {service_type} ===")
        listener = ServiceInstanceListener(service_type)
        ServiceBrowser(zeroconf, service_type, listener)
        time.sleep(2)

    zeroconf.close()
    print("[SCAN COMPLETE]")


if __name__ == "__main__":
    full_mdns_scan()
