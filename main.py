import json
import os
import time
from collections import deque
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

from common import (
    config_path,
    log_path,
    read_json,
    status_path,
    write_json_atomic,
)

MAX_LOG_LINES = 500
FIRST_LOAD_BYTES = 200 * 1024
SERVICE_NAME = "Udpservice"  # khớp với `services = udpservice:...` trong buildozer.spec
KNOWN_KEYS = {"voltage_v", "wake", "time", "time_valid"}

KV = """
<LogLine@Label>:
    size_hint_y: None
    height: dp(22)
    font_size: '12sp'
    halign: 'left'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    text_size: self.width, None

<FieldRow>:
    size_hint_y: None
    height: dp(34)
    Label:
        text: root.title
        color: .65, .65, .65, 1
        size_hint_x: .42
        font_size: '14sp'
        halign: 'left'
        valign: 'middle'
        text_size: self.size
    Label:
        text: root.value
        bold: True
        font_size: '18sp'
        halign: 'left'
        valign: 'middle'
        text_size: self.size

<Root>:
    orientation: 'vertical'
    padding: dp(8)
    spacing: dp(4)

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
            width: dp(80)
            disabled: root.running
        Button:
            text: 'Dừng' if root.running else 'Bắt đầu'
            on_release: root.toggle()
        Button:
            text: 'Pin'
            size_hint_x: None
            width: dp(55)
            on_release: root.open_battery_settings()
        Button:
            text: 'Xóa'
            size_hint_x: None
            width: dp(55)
            on_release: root.clear_view()

    Label:
        text: root.status
        size_hint_y: None
        height: dp(24)
        font_size: '13sp'
        halign: 'left'
        text_size: self.width, None

    FieldRow:
        title: 'Điện áp'
        value: root.f_voltage
    FieldRow:
        title: 'Nguyên nhân thức dậy'
        value: root.f_wake
    FieldRow:
        title: 'Thời gian thiết bị'
        value: root.f_time
    FieldRow:
        title: 'Giờ thiết bị hợp lệ'
        value: root.f_valid
    FieldRow:
        title: 'Trường khác'
        value: root.f_extra
    FieldRow:
        title: 'Nhận lúc'
        value: root.f_rx
    FieldRow:
        title: 'Từ địa chỉ'
        value: root.f_from
    FieldRow:
        title: 'Số gói (phiên này)'
        value: root.f_count

    BoxLayout:
        size_hint_y: None
        height: dp(34)
        Label:
            text: 'Tự cuộn xuống'
            font_size: '13sp'
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

    Label:
        text: root.log_file
        size_hint_y: None
        height: dp(34)
        font_size: '10sp'
        color: .6, .6, .6, 1
        halign: 'left'
        valign: 'middle'
        text_size: self.width, self.height
"""


# ---------------------------------------------------------------- tiện ích
def fmt_time(s, fmt="%d/%m/%Y %H:%M:%S"):
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(str(s)).strftime(fmt)
    except Exception:
        return str(s)


def summarize(rec):
    t = fmt_time(rec.get("rx"), "%H:%M:%S")
    d = rec.get("data")
    if isinstance(d, dict):
        parts = []
        if "voltage_v" in d:
            parts.append("%sV" % d["voltage_v"])
        if "wake" in d:
            parts.append(str(d["wake"]))
        if "time_valid" in d:
            parts.append("giờ OK" if d["time_valid"] else "giờ chưa đúng")
        if not parts:
            parts.append(json.dumps(d, ensure_ascii=False))
        return "[%s] %s" % (t, " | ".join(parts))
    return "[%s] %s" % (t, rec.get("raw", ""))


# ------------------------------------------------- điều khiển service Android
def _service_class():
    from android import mActivity
    from jnius import autoclass

    pkg = str(mActivity.getApplicationContext().getPackageName())
    return autoclass(pkg + ".Service" + SERVICE_NAME), mActivity


def start_service():
    """Trả về None nếu OK, hoặc chuỗi lỗi."""
    if platform != "android":
        return "Không phải Android: hãy chạy `python service.py` ở terminal khác để thử."
    try:
        svc, act = _service_class()
        try:
            svc.start(act, "")
        except Exception:
            svc.start(act, "", "UDP Receiver", "Đang nhận dữ liệu UDP", "")
        return None
    except Exception as e:
        return "Không khởi động được service: %s" % e


def stop_service():
    if platform != "android":
        return
    try:
        svc, act = _service_class()
        svc.stop(act)
    except Exception:
        pass


class FieldRow(BoxLayout):
    title = StringProperty("")
    value = StringProperty("—")


class Root(BoxLayout):
    running = BooleanProperty(False)
    autoscroll = BooleanProperty(True)
    status = StringProperty("Chưa chạy")
    log_file = StringProperty("")

    f_voltage = StringProperty("—")
    f_wake = StringProperty("—")
    f_time = StringProperty("—")
    f_valid = StringProperty("—")
    f_extra = StringProperty("—")
    f_rx = StringProperty("—")
    f_from = StringProperty("—")
    f_count = StringProperty("0")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lines = deque(maxlen=MAX_LOG_LINES)
        self._cur_path = None
        self._offset = None
        self._starting_until = 0.0
        self._ignore_alive_until = 0.0
        self._msg = ""

        cfg = read_json(config_path(), {}) or {}
        if cfg.get("port"):
            self.ids.port_input.text = str(cfg["port"])

        Clock.schedule_interval(self._poll, 0.5)

    # --------------------------------------------------------- nút bấm
    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        try:
            port = int(self.ids.port_input.text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self._msg = "Port không hợp lệ"
            return
        write_json_atomic(config_path(), {"port": port})
        err = start_service()
        self._msg = err or ""
        if not err:
            self._ignore_alive_until = 0.0
            self._starting_until = time.time() + 8

    def stop(self):
        stop_service()
        self._starting_until = 0.0
        self._ignore_alive_until = time.time() + 4
        write_json_atomic(status_path(), {"alive": 0})
        self._msg = ""

    def clear_view(self):
        """Chỉ xóa phần hiển thị, KHÔNG xóa file log."""
        self._lines.clear()
        self.ids.rv.data = []

    def open_battery_settings(self):
        if platform != "android":
            return
        try:
            from android import mActivity
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            mActivity.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        except Exception as e:
            self._msg = "Không mở được cài đặt pin: %s" % e

    # ------------------------------------------------------ vòng cập nhật
    def _poll(self, dt):
        st = read_json(status_path(), {}) or {}
        now = time.time()
        alive = (now - float(st.get("alive", 0) or 0) < 6) and now > self._ignore_alive_until
        self.running = alive or now < self._starting_until

        if st.get("error") and alive:
            self.status = st["error"]
        elif alive:
            self.status = "Đang nhận trên port %s (service chạy nền)" % st.get("port", "?")
        elif self.running:
            self.status = "Đang khởi động service..."
        else:
            self.status = self._msg or "Đã dừng"
        if alive:
            self.f_count = str(st.get("count", 0))

        self._read_new_lines()

    def _read_new_lines(self):
        path = log_path()
        self.log_file = "Log: " + path
        if path != self._cur_path:
            self._cur_path = path
            self._offset = None
        if not os.path.exists(path):
            return
        size = os.path.getsize(path)
        first = self._offset is None
        if first:
            self._offset = max(0, size - FIRST_LOAD_BYTES)
        if size <= self._offset:
            return

        with open(path, "rb") as f:
            f.seek(self._offset)
            chunk = f.read(256 * 1024)
        if first and self._offset > 0:  # bỏ dòng đầu bị cắt dở
            i = chunk.find(b"\n")
            if i < 0:
                return
            self._offset += i + 1
            chunk = chunk[i + 1:]
        end = chunk.rfind(b"\n")
        if end < 0:  # chưa có dòng hoàn chỉnh
            return
        self._offset += end + 1

        last = None
        for raw in chunk[:end].split(b"\n"):
            try:
                rec = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            self._lines.append(summarize(rec))
            last = rec
        if last is None:
            return

        self.ids.rv.data = [{"text": l} for l in self._lines]
        if self.autoscroll:
            self.ids.rv.scroll_y = 0
        self._show_record(last)

    def _show_record(self, rec):
        self.f_rx = fmt_time(rec.get("rx"))
        self.f_from = rec.get("from", "—")
        d = rec.get("data")
        if not isinstance(d, dict):
            self.f_extra = rec.get("raw", "—")
            return
        v = d.get("voltage_v")
        if isinstance(v, (int, float)):
            self.f_voltage = "%.2f V" % v
        else:
            self.f_voltage = "—" if v is None else str(v)
        self.f_wake = str(d.get("wake", "—"))
        self.f_time = fmt_time(d.get("time"))
        tv = d.get("time_valid")
        self.f_valid = "Có" if tv is True else "Không" if tv is False else "—"
        extra = {k: val for k, val in d.items() if k not in KNOWN_KEYS}
        self.f_extra = ", ".join("%s=%s" % kv for kv in extra.items()) or "—"


class UDPReceiverApp(App):
    def build(self):
        Builder.load_string(KV)
        return Root()

    def on_start(self):
        if platform == "android":
            try:
                from android.permissions import request_permissions

                request_permissions(["android.permission.POST_NOTIFICATIONS"])
            except Exception:
                pass

    def on_pause(self):
        return True  # service vẫn chạy nền, giao diện chỉ tạm dừng


if __name__ == "__main__":
    UDPReceiverApp().run()
