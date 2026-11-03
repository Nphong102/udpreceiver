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
requirements = python3,kivy

# (str) Supported orientations (landscape, portrait or all)
orientation = portrait

# (list) Permissions
android.permissions = INTERNET

# (str) Version of the application
version = 1.1.0

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 29

# (bool) Indicate whether the application should be fullscreen or not
fullscreen = 0

# Chỉ định phiên bản NDK ổn định để tránh lỗi build
android.ndk = 25b

# Tự động chấp nhận giấy phép SDK, cần thiết cho CI/CD
android.accept_sdk_license = True

[buildozer]

# (int) Log level
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
