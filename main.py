import socket
import threading
import time
from collections import deque

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

MAX_LOG_LINES = 500  # giữ tối đa 500 dòng log

KV = """
<LogLine@Label>:
    size_hint_y: None
    height: dp(22)
    font_size: '13sp'
    halign: 'left'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    text_size: self.width, None

<Root>:
    orientation: 'vertical'
    padding: dp(8)
    spacing: dp(6)

    BoxLayout:
        size_hint_y: None
        height: dp(44)
        spacing: dp(6)
        Label:
            text: 'Port:'
            size_hint_x: None
            width: dp(45)
        TextInput:
            id: port_input
            text: '5005'
            input_filter: 'int'
            multiline: False
            size_hint_x: None
            width: dp(90)
            disabled: root.running
        Button:
            text: 'Stop' if root.running else 'Start'
            on_release: root.toggle()
        Button:
            text: 'Clear'
            size_hint_x: None
            width: dp(70)
            on_release: root.clear_log()

    Label:
        text: root.status
        size_hint_y: None
        height: dp(24)
        font_size: '13sp'
        halign: 'left'
        text_size: self.width, None

    Label:
        text: root.latest
        size_hint_y: None
        height: dp(70)
        font_size: '20sp'
        bold: True
        halign: 'center'
        valign: 'middle'
        text_size: self.width, self.height

    BoxLayout:
        size_hint_y: None
        height: dp(36)
        Label:
            text: 'Tự cuộn xuống'
        Switch:
            active: root.autoscroll
            on_active: root.autoscroll = self.active
            size_hint_x: None
            width: dp(80)

    RecycleView:
        id: rv
        viewclass: 'LogLine'
        scroll_type: ['bars', 'content']
        bar_width: dp(6)
        RecycleBoxLayout:
            default_size: None, dp(22)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: 'vertical'
"""


class Root(BoxLayout):
    running = BooleanProperty(False)
    autoscroll = BooleanProperty(True)
    status = StringProperty("Chưa chạy")
    latest = StringProperty("(chưa có dữ liệu)")
    count = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._queue = deque()  # luồng mạng đẩy vào, UI lấy ra
        self._lines = deque(maxlen=MAX_LOG_LINES)
        Clock.schedule_interval(self._flush, 0.2)

    # ---------- điều khiển ----------
    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        try:
            port = int(self.ids.port_input.text)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
            sock.settimeout(0.5)
        except Exception as e:
            self.status = f"Lỗi mở port: {e}"
            return
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        self.running = True
        self.status = f"Đang nghe UDP port {port}"
        self._queue.append(self._stamp(f"--- Bắt đầu nghe port {port} ---"))

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self.running = False
        self.status = f"Đã dừng. Tổng gói nhận: {self.count}"
        self._queue.append(self._stamp("--- Đã dừng ---"))

    def clear_log(self):
        self._queue.clear()
        self._lines.clear()
        self.count = 0
        self.latest = "(chưa có dữ liệu)"
        self.ids.rv.data = []

    # ---------- luồng nhận dữ liệu ----------
    def _recv_loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            text = data.decode("utf-8", errors="replace").strip()
            self._queue.append(
                (self._stamp(f"{addr[0]}:{addr[1]}  {text}"), text)
            )

    @staticmethod
    def _stamp(msg):
        return f"[{time.strftime('%H:%M:%S')}] {msg}"

    # ---------- cập nhật giao diện (chạy trên luồng UI) ----------
    def _flush(self, dt):
        if not self._queue:
            return
        changed = False
        while self._queue:
            item = self._queue.popleft()
            if isinstance(item, tuple):  # gói dữ liệu thật
                line, text = item
                self.count += 1
                self.latest = text
            else:  # dòng thông báo hệ thống
                line = item
            self._lines.append(line)
            changed = True
        if changed:
            self.ids.rv.data = [{"text": l} for l in self._lines]
            if self.autoscroll:
                self.ids.rv.scroll_y = 0
            if self.running:
                self.status = (
                    f"Đang nghe port {self.ids.port_input.text} "
                    f"| Đã nhận: {self.count} gói"
                )


class UDPReceiverApp(App):
    def build(self):
        Builder.load_string(KV)
        return Root()

    def on_pause(self):
        return True  # giữ app chạy khi chuyển sang app khác

    def on_stop(self):
        root = self.root
        if root and root.running:
            root.stop()


if __name__ == "__main__":
    UDPReceiverApp().run()
