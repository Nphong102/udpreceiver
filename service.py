"""Service nhận UDP chạy nền (foreground service).

- Giữ WakeLock + WifiLock + MulticastLock để nhận được khi tắt màn hình.
- Mỗi gói nhận được ghi thành 1 dòng JSON vào file log theo ngày.
- Ghi status.json (heartbeat) để giao diện biết service còn sống.
"""
import json
import os
import socket
import time
from datetime import datetime

from common import (
    config_path,
    log_path,
    read_json,
    status_path,
    write_json_atomic,
)


def acquire_locks():
    held = []
    try:
        from jnius import autoclass

        PythonService = autoclass("org.kivy.android.PythonService")
        ctx = PythonService.mService.getApplicationContext()
        Context = autoclass("android.content.Context")
        PowerManager = autoclass("android.os.PowerManager")
        WifiManager = autoclass("android.net.wifi.WifiManager")
    except Exception as e:
        print("udpservice: không có jnius/Android:", e)
        return held

    try:
        pm = ctx.getSystemService(Context.POWER_SERVICE)
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "udpreceiver:cpu")
        wl.setReferenceCounted(False)
        wl.acquire()
        held.append(wl)
    except Exception as e:
        print("udpservice: WakeLock lỗi:", e)

    try:
        wm = ctx.getSystemService(Context.WIFI_SERVICE)
        wfl = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "udpreceiver:wifi")
        wfl.setReferenceCounted(False)
        wfl.acquire()
        held.append(wfl)
        mc = wm.createMulticastLock("udpreceiver:mcast")
        mc.setReferenceCounted(False)
        mc.acquire()
        held.append(mc)
    except Exception as e:
        print("udpservice: WifiLock/MulticastLock lỗi:", e)
    return held


def get_port():
    arg = os.environ.get("PYTHON_SERVICE_ARGUMENT", "").strip()
    if arg.isdigit():
        return int(arg)
    cfg = read_json(config_path(), {}) or {}
    try:
        return int(cfg.get("port", 5005))
    except Exception:
        return 5005


def run():
    port = get_port()
    acquire_locks()

    sock = None
    count = 0
    last_rx = ""
    err = ""
    last_write = 0.0

    def write_status(force=False):
        nonlocal last_write
        now = time.time()
        if not force and now - last_write < 1.0:
            return
        last_write = now
        write_json_atomic(
            status_path(),
            {
                "alive": now,
                "port": port,
                "count": count,
                "last_rx": last_rx,
                "error": err,
            },
        )

    while True:
        if sock is None:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", port))
                sock.settimeout(1.0)
                err = ""
            except Exception as e:
                err = "Không mở được port %s: %s" % (port, e)
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None
                write_status(force=True)
                time.sleep(3)
                continue
            write_status(force=True)

        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            write_status()
            continue
        except OSError as e:
            err = "Lỗi socket: %s" % e
            try:
                sock.close()
            except Exception:
                pass
            sock = None
            time.sleep(1)
            continue

        rx = datetime.now().astimezone().isoformat(timespec="seconds")
        text = data.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None

        record = {"rx": rx, "from": addr[0]}
        if payload is not None:
            record["data"] = payload
        else:
            record["raw"] = text

        try:
            with open(log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            err = "Không ghi được log: %s" % e

        count += 1
        last_rx = rx
        write_status()


if __name__ == "__main__":
    run()
