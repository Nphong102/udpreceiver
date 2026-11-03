import json
import os
import time
from collections import deque
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ColorProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
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

GREEN = (0.24, 0.86, 0.59, 1)
RED = (1.0, 0.40, 0.40, 1)
WHITE = (1, 1, 1, 1)

KV = """
<Card>:
    padding: dp(12)
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]

<InfoCard>:
    orientation: 'vertical'
    size_hint_y: None
    height: dp(64)
    spacing: dp(2)
    Label:
        text: root.title
        font_size: '11sp'
        color: .55, .60, .66, 1
        halign: 'left'
        valign: 'bottom'
        text_size: self.size
    Label:
        text: root.value
        font_size: '16sp'
        bold: True
        color: root.v_color
        halign: 'left'
        valign: 'top'
        shorten: True
        text_size: self.size

<PillButton>:
    color: 1, 1, 1, 1
    bold: True
    canvas.before:
        Color:
            rgba: self.bg if self.state == 'normal' else [self.bg[0] * .75, self.bg[1] * .75, self.bg[2] * .75, 1]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2]

<LogLine@Label>:
    size_hint_y: None
    height: dp(22)
    font_size: '12sp'
    color: .82, .86, .90, 1
    halign: 'left'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    text_size: self.width, None

<Root>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(8)

    # ---------- tiêu đề + trạng thái ----------
    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        BoxLayout:
            orientation: 'vertical'
            Label:
                text: 'UDP Receiver'
                font_size: '20sp'
                bold: True
                halign: 'left'
                valign: 'middle'
                text_size: self.size
            Label:
                text: root.status
                font_size: '12sp'
                color: .55, .60, .66, 1
                halign: 'left'
                valign: 'middle'
                shorten: True
                text_size: self.size
        Widget:
            size_hint: None, None
            size: dp(10), dp(10)
            pos_hint: {'center_y': .5}
            canvas:
                Color:
                    rgba: (.24, .86, .59, 1) if root.running else (.55, .60, .66, 1)
                Ellipse:
                    pos: self.pos
                    size: self.size
        Label:
            text: 'Đang chạy' if root.running else 'Đã dừng'
            font_size: '13sp'
            size_hint_x: None
            width: dp(70)
            color: (.24, .86, .59, 1) if root.running else (.55, .60, .66, 1)
            halign: 'left'
            valign: 'middle'
            text_size: self.size

    # ---------- thẻ điện áp ----------
    Card:
        orientation: 'vertical'
        size_hint_y: None
        height: dp(128)
        bg: .10, .19, .30, 1
        Label:
            text: 'ĐIỆN ÁP'
            font_size: '12sp'
            bold: True
            color: .55, .72, .92, 1
            size_hint_y: None
            height: dp(20)
            halign: 'left'
            valign: 'bottom'
            text_size: self.size
        Label:
            text: root.f_voltage
            font_size: '46sp'
            bold: True
            halign: 'left'
            valign: 'middle'
            text_size: self.size
        Label:
            text: root.f_sub
            font_size: '12sp'
            color: .55, .72, .92, 1
            size_hint_y: None
            height: dp(20)
            halign: 'left'
            valign: 'top'
            shorten: True
            text_size: self.size

    # ---------- các trường ----------
    BoxLayout:
        size_hint_y: None
        height: dp(64)
        spacing: dp(8)
        InfoCard:
            title: 'NGUYÊN NHÂN THỨC DẬY'
            value: root.f_wake
        InfoCard:
            title: 'GIỜ THIẾT BỊ HỢP LỆ'
            value: root.f_valid
            v_color: root.valid_color
    InfoCard:
        title: 'THỜI GIAN THIẾT BỊ'
        value: root.f_time
    BoxLayout:
        size_hint_y: None
        height: dp(64)
        spacing: dp(8)
        InfoCard:
            title: 'SỐ GÓI (PHIÊN NÀY)'
            value: root.f_count
        InfoCard:
            title: 'TỪ ĐỊA CHỈ'
            value: root.f_from

    # ---------- nhật ký ----------
    Card:
        orientation: 'vertical'
        spacing: dp(6)
        BoxLayout:
            size_hint_y: None
            height: dp(30)
            spacing: dp(6)
            Label:
                text: 'Nhật ký'
                font_size: '14sp'
                bold: True
                halign: 'left'
                valign: 'middle'
                text_size: self.size
            PillButton:
                text: 'Tự cuộn: Bật' if root.autoscroll else 'Tự cuộn: Tắt'
                font_size: '12sp'
                size_hint_x: None
                width: dp(112)
                bg: (.24, .86, .59, .55) if root.autoscroll else (.22, .28, .34, 1)
                on_release: root.autoscroll = not root.autoscroll
            PillButton:
                text: 'Xóa'
                font_size: '12sp'
                size_hint_x: None
                width: dp(56)
                bg: .22, .28, .34, 1
                on_release: root.clear_view()
        RecycleView:
            id: rv
            viewclass: 'LogLine'
            scroll_type: ['bars', 'content']
            bar_width: dp(5)
            RecycleBoxLayout:
                default_size: None, dp(22)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
        Label:
            text: root.log_file
            size_hint_y: None
            height: dp(26)
            font_size: '9sp'
            color: .45, .50, .56, 1
            halign: 'left'
            valign: 'middle'
            text_size: self.size

    # ---------- thanh điều khiển ----------
    BoxLayout:
        size_hint_y: None
        height: dp(52)
        spacing: dp(8)
        Card:
            size_hint_x: None
            width: dp(88)
            padding: 0
            bg: .13, .17, .21, 1
            TextInput:
                id: port_input
                hint_text: 'Port'
                text: '5005'
                input_filter: 'int'
                multiline: False
                halign: 'center'
                padding: [dp(8), (self.height - self.line_height) / 2]
                background_normal: ''
                background_active: ''
                background_disabled_normal: ''
                background_color: 0, 0, 0, 0
                foreground_color: 1, 1, 1, 1
                disabled_foreground_color: .55, .60, .66, 1
                hint_text_color: .45, .50, .56, 1
                cursor_color: .24, .86, .59, 1
                disabled: root.running
        PillButton:
            text: 'DỪNG' if root.running else 'BẮT ĐẦU'
            font_size: '16sp'
            bg: (.90, .36, .36, 1) if root.running else (.24, .78, .55, 1)
            color: (1, 1, 1, 1) if root.running else (.03, .10, .07, 1)
            on_release: root.toggle()
        PillButton:
            text: 'Pin'
            size_hint_x: None
            width: dp(60)
            bg: .22, .28, .34, 1
            on_release: root.open_battery_settings()
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


# ------------------------------------------------------------ widget giao diện
class Card(BoxLayout):
    bg = ColorProperty([0.10, 0.13, 0.16, 1])


class InfoCard(Card):
    title = StringProperty("")
    value = StringProperty("—")
    v_color = ColorProperty(WHITE)


class PillButton(ButtonBehavior, Label):
    bg = ColorProperty([0.22, 0.28, 0.34, 1])


class Root(BoxLayout):
    running = BooleanProperty(False)
    autoscroll = BooleanProperty(True)
    status = StringProperty("Chưa chạy")
    log_file = StringProperty("")

    f_voltage = StringProperty("—")
    f_sub = StringProperty("Chưa có dữ liệu")
    f_wake = StringProperty("—")
    f_time = StringProperty("—")
    f_valid = StringProperty("—")
    valid_color = ColorProperty(WHITE)
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
            self.status = "Đang nghe port %s · chạy nền" % st.get("port", "?")
        elif self.running:
            self.status = "Đang khởi động service..."
        else:
            self.status = self._msg or "Nhấn BẮT ĐẦU để nhận dữ liệu"
        if alive:
            self.f_count = str(st.get("count", 0))

        self._read_new_lines()

    def _read_new_lines(self):
        path = log_path()
        self.log_file = path
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
        rx = fmt_time(rec.get("rx"))
        self.f_from = rec.get("from", "—")
        d = rec.get("data")
        if not isinstance(d, dict):
            self.f_sub = "Nhận lúc %s  |  %s" % (rx, rec.get("raw", ""))
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
        self.valid_color = GREEN if tv is True else RED if tv is False else WHITE
        extra = {k: val for k, val in d.items() if k not in KNOWN_KEYS}
        sub = "Nhận lúc %s" % rx
        if extra:
            sub += "  |  " + ", ".join("%s=%s" % kv for kv in extra.items())
        self.f_sub = sub


class UDPReceiverApp(App):
    def build(self):
        Window.clearcolor = (0.059, 0.078, 0.098, 1)
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
