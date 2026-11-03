[app]
title = UDPReceiver
package.name = udpreceiver
package.domain = org.np102
source.include_exts = py,png,jpg,kv,atlas
source.dir = .
requirements = python3,kivy
orientation = portrait
android.permissions = INTERNET
version = 1.1.0
android.api = 33
android.minapi = 29
android.ndk = 25b
android.accept_sdk_license = True
fullscreen = 0
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1