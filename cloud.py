"""Đẩy log lên Firebase Realtime Database bằng REST (không cần SDK).

Cách hoạt động:
  - Nguồn dữ liệu chính là các file log udp_log_YYYY-MM-DD.jsonl (không bao giờ bị xóa).
  - upload_state.json nhớ đã gửi tới byte nào của file nào -> mất mạng / tắt máy
    vẫn tiếp tục gửi đúng chỗ, không mất gói nào.
  - Mỗi dòng log có key cố định (ngày + vị trí byte) nên gửi lại cũng không bị trùng.
  - Đăng nhập Anonymous của Firebase Auth; token tự làm mới.
"""
import glob
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from common import config_path, get_data_dir, read_json, write_json_atomic

try:
    import firebase_config as fc
except Exception:  # chưa có file cấu hình
    fc = None

BATCH_MAX = 100
CHUNK_BYTES = 256 * 1024
BAD_KEY_CHARS = set(".$#[]/")


def _cfg(name, default=""):
    return getattr(fc, name, default) if fc is not None else default


def make_ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    ctx = ssl.create_default_context()
    try:  # kho chứng chỉ của Android
        if os.path.isdir("/system/etc/security/cacerts"):
            ctx.load_verify_locations(capath="/system/etc/security/cacerts")
    except Exception:
        pass
    return ctx


class HttpError(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP %s: %s" % (code, body[:200]))
        self.code = code
        self.body = body


def http_json(method, url, payload=None, form=None, timeout=15, ctx=None):
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", "replace"))
    return json.loads(body) if body.strip() else None


def clean_key(k):
    return "".join("_" if c in BAD_KEY_CHARS else c for c in str(k)) or "_"


def sanitize(o):
    """Firebase không cho key chứa . $ # [ ] /"""
    if isinstance(o, dict):
        return {clean_key(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sanitize(v) for v in o]
    return o


class Auth:
    """Đăng nhập ẩn danh (Anonymous) qua Firebase Auth REST."""

    def __init__(self, api_key, ctx):
        self.key = api_key
        self.ctx = ctx
        self.path = os.path.join(get_data_dir(), "auth.json")
        d = read_json(self.path, {}) or {}
        self.id_token = d.get("id_token")
        self.refresh = d.get("refresh_token")
        self.uid = d.get("uid", "")
        self.exp = float(d.get("exp", 0) or 0)

    def _save(self):
        write_json_atomic(
            self.path,
            {
                "id_token": self.id_token,
                "refresh_token": self.refresh,
                "uid": self.uid,
                "exp": self.exp,
            },
        )

    def token(self, force=False):
        now = time.time()
        if self.id_token and not force and now < self.exp - 120:
            return self.id_token
        if self.refresh:
            try:
                r = http_json(
                    "POST",
                    "https://securetoken.googleapis.com/v1/token?key=" + self.key,
                    form={"grant_type": "refresh_token", "refresh_token": self.refresh},
                    ctx=self.ctx,
                )
                self.id_token = r["id_token"]
                self.refresh = r.get("refresh_token", self.refresh)
                self.uid = r.get("user_id", self.uid)
                self.exp = now + int(r.get("expires_in", 3600))
                self._save()
                return self.id_token
            except HttpError as e:
                if e.code not in (400, 401):
                    raise
        r = http_json(
            "POST",
            "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + self.key,
            payload={"returnSecureToken": True},
            ctx=self.ctx,
        )
        self.id_token = r["idToken"]
        self.refresh = r["refreshToken"]
        self.uid = r.get("localId", "")
        self.exp = now + int(r.get("expiresIn", 3600))
        self._save()
        return self.id_token


class Uploader(threading.Thread):
    def __init__(self, info):
        super().__init__(daemon=True)
        self.info = info
        self.info.update(
            enabled=False, uploaded=0, skipped=0, pending_kb=0, error="", uid="", last_ok=0
        )
        self.ctx = make_ssl_context()
        self.auth = None

    # ------------------------------------------------------------ vòng lặp
    def run(self):
        while True:
            delay = 5
            try:
                delay = self.step()
            except HttpError as e:
                if "ADMIN_ONLY_OPERATION" in e.body or "OPERATION_NOT_ALLOWED" in e.body:
                    self.info["error"] = "Chưa bật Anonymous sign-in trong Firebase Auth"
                    delay = 30
                elif e.code in (401, 403):
                    self.info["error"] = "Firebase từ chối (%s): kiểm tra Rules / API key" % e.code
                    delay = 30
                else:
                    self.info["error"] = "Firebase lỗi %s: %s" % (e.code, e.body[:80])
                    delay = 15
            except (urllib.error.URLError, OSError, ssl.SSLError):
                self.info["error"] = "Mất kết nối, sẽ thử lại"
                delay = 10
            except Exception as e:
                self.info["error"] = str(e)[:100]
                delay = 15
            time.sleep(delay)

    # ------------------------------------------------------------ một bước
    def step(self):
        info = self.info
        cfg = read_json(config_path(), {}) or {}
        info["enabled"] = bool(cfg.get("upload"))
        if not info["enabled"]:
            info["error"] = ""
            return 3

        base = str(_cfg("DATABASE_URL")).strip().rstrip("/")
        if not base:
            info["error"] = "Chưa điền DATABASE_URL trong firebase_config.py"
            return 5
        root = str(_cfg("DB_ROOT", "udp_receiver")).strip("/") or "udp_receiver"
        api_key = str(_cfg("API_KEY")).strip()

        data_dir = get_data_dir()
        state_file = os.path.join(data_dir, "upload_state.json")
        files = sorted(
            os.path.basename(p) for p in glob.glob(os.path.join(data_dir, "udp_log_*.jsonl"))
        )
        if not files:
            info["pending_kb"] = 0
            return 3

        state = read_json(state_file, {}) or {}
        cur = state.get("file")
        off = int(state.get("offset", 0) or 0)
        if cur not in files:
            newer = [f for f in files if cur is None or f > cur]
            cur = newer[0] if newer else files[-1]
            off = 0
        path = os.path.join(data_dir, cur)
        size = os.path.getsize(path)
        if off > size:
            off = 0
        self._pending(data_dir, files, cur, off)

        if off >= size:  # file này đã gửi hết
            i = files.index(cur)
            if i + 1 < len(files):
                write_json_atomic(state_file, {"file": files[i + 1], "offset": 0})
                return 0.1
            info["error"] = ""
            return 3

        with open(path, "rb") as f:
            f.seek(off)
            chunk = f.read(CHUNK_BYTES)
        end = chunk.rfind(b"\n")
        if end < 0:  # dòng cuối chưa ghi xong
            return 2

        date = cur[len("udp_log_"):-len(".jsonl")]
        items = []
        consumed = off
        for raw in chunk[:end].split(b"\n"):
            if len(items) >= BATCH_MAX:
                break
            line_start = consumed
            consumed += len(raw) + 1
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            rec = sanitize(rec)
            try:
                rec["ts"] = datetime.fromisoformat(rec["rx"]).timestamp()
            except Exception:
                pass
            items.append(("%s_%09d" % (date, line_start), rec))

        if items:
            self._send_items(base, root, api_key, items)
        write_json_atomic(state_file, {"file": cur, "offset": consumed})
        self._pending(data_dir, files, cur, consumed)
        info["error"] = ""
        info["last_ok"] = time.time()
        return 0.2 if consumed < size else 3

    # ------------------------------------------------------------ gửi
    def _send_items(self, base, root, api_key, items):
        try:
            self._patch(base, root, api_key, dict(items))
            self.info["uploaded"] += len(items)
        except HttpError as e:
            if e.code == 400 and len(items) > 1:  # tách đôi để tìm gói lỗi định dạng
                mid = len(items) // 2
                self._send_items(base, root, api_key, items[:mid])
                self._send_items(base, root, api_key, items[mid:])
            elif e.code == 400:
                self.info["skipped"] += 1  # bỏ qua gói lỗi để không kẹt hàng đợi (log gốc vẫn còn)
            else:
                raise

    def _patch(self, base, root, api_key, batch):
        url = "%s/%s/readings.json?print=silent" % (base, root)
        for attempt in (0, 1):
            tok = self._token(api_key, force=(attempt == 1))
            u = url + ("&auth=" + urllib.parse.quote(tok) if tok else "")
            try:
                http_json("PATCH", u, payload=batch, ctx=self.ctx)
                return
            except HttpError as e:
                if e.code == 401 and tok and attempt == 0:
                    continue  # token hết hạn -> làm mới rồi thử lại
                raise

    def _token(self, api_key, force=False):
        if not api_key:
            return None  # không dùng đăng nhập (Rules đang mở)
        if self.auth is None or self.auth.key != api_key:
            self.auth = Auth(api_key, self.ctx)
        tok = self.auth.token(force)
        self.info["uid"] = self.auth.uid
        return tok

    def _pending(self, data_dir, files, cur, off):
        total = 0
        for f in files:
            if f < cur:
                continue
            try:
                size = os.path.getsize(os.path.join(data_dir, f))
            except OSError:
                continue
            total += max(0, size - (off if f == cur else 0))
        self.info["pending_kb"] = int(round(total / 1024.0))
