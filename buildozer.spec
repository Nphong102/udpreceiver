[app]

# (str) Title of your application
title = UDPReceiver

# (str) Package name
package.name = udpreceiver

# (str) Package domain (needed for android packaging)
package.domain = org.np102

# (str) Source files to include (let git decide or specify manually)
source.include_exts = py,png,jpg,kv,atlas

# (str) Directory where the source code is located
source.dir = .

# (list) Application requirements
# Lưu ý: socket là thư viện chuẩn của Python nên không cần khai báo ở đây
requirements = python3,kivy

# (str) Supported orientations (landscape, portrait or all)
orientation = portrait

# (list) Permissions
# Cực kỳ quan trọng để ứng dụng nhận gói tin mạng từ ESP32
android.permissions = INTERNET

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support (Đã đặt là 10 tương ứng API 29)
android.minapi = 29

# (bool) Indicate whether the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color
# android.presplash_color = #FFFFFF

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1