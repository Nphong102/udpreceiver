[app]
title = UDPReceiver
package.name = udpreceiver
package.domain = org.np102
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.3.0
requirements = python3,kivy==2.3.0,certifi
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK,FOREGROUND_SERVICE,POST_NOTIFICATIONS

# Service chạy nền: tên:file:foreground
services = udpservice:service.py:foreground

android.api = 33
android.minapi = 29
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
