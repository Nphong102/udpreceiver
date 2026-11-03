"""Hàm dùng chung cho giao diện (main.py) và service (service.py).

Hai bên chạy ở hai tiến trình khác nhau nên trao đổi với nhau qua file
trong thư mục dữ liệu của app:
  - config.json            : giao diện ghi (port), service đọc
  - status.json            : service ghi (heartbeat, số gói), giao diện đọc
  - udp_log_YYYY-MM-DD.jsonl : service ghi log, giao diện đọc phần mới
"""
import json
import os
from datetime import datetime


def get_data_dir():
    """Thư mục lưu dữ liệu. Trên Android: Android/data/<package>/files/"""
    path = None
    try:
        from jnius import autoclass

        ctx = None
        try:
            from android import mActivity

            ctx = mActivity
        except Exception:
            ctx = None
        if ctx is None:  # đang chạy trong service
            ctx = autoclass("org.kivy.android.PythonService").mService
        d = ctx.getExternalFilesDir(None)
        if d is not None:
            path = d.getAbsolutePath()
        else:
            path = ctx.getFilesDir().getAbsolutePath()
    except Exception:
        path = os.path.join(os.getcwd(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def log_path():
    name = "udp_log_%s.jsonl" % datetime.now().strftime("%Y-%m-%d")
    return os.path.join(get_data_dir(), name)


def status_path():
    return os.path.join(get_data_dir(), "status.json")


def config_path():
    return os.path.join(get_data_dir(), "config.json")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass
