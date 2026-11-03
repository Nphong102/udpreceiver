import socket
import threading
from kivy.app import App
from kivy.uix.label import Label
from kivy.clock import Clock

class UDPReceiverApp(App):
    def build(self):
        # Tạo nhãn hiển thị dữ liệu trên màn hình
        self.label = Label(
            text="Đang chờ dữ liệu từ ESP32...", 
            font_size=24,
            halign="center"
        )
        
        # Chạy luồng phụ (Thread) để lắng nghe UDP
        self.running = True
        self.thr = threading.Thread(target=self.listen_udp)
        self.thr.daemon = True
        self.thr.start()
        
        return self.label

    def listen_udp(self):
        UDP_IP = ""  # Lắng nghe tất cả các card mạng
        UDP_PORT = 8888  # Đổi sang cổng 8888 (tránh port 6000 hay bị chặn/xung đột)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((UDP_IP, UDP_PORT))
            sock.settimeout(1.0)  # Đặt timeout để luồng có thể thoát khi đóng App
        except Exception as e:
            print(f"Lỗi khởi tạo Socket (Có thể do trùng port): {e}")
            return

        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                
                # Cập nhật giao diện an toàn thông qua Clock 
                # Dùng m=message, a=addr để chốt giá trị tại thời điểm nhận, tránh trôi dữ liệu
                Clock.schedule_once(lambda dt, m=message, a=addr: self.update_label(m, a))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Lỗi khi nhận dữ liệu: {e}")
                
        sock.close()

    def update_label(self, message, addr):
        # Hàm cập nhật chữ lên màn hình điện thoại/máy tính
        self.label.text = f"Nhận từ ESP32 ({addr[0]}):\n\n{message}"

    def on_stop(self):
        # Dừng luồng khi tắt ứng dụng
        self.running = False

if __name__ == "__main__":
    UDPReceiverApp().run()
