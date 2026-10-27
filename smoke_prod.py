"""Живая проверка production-сервера (waitress) по HTTP."""
import io
import re
import sys
import urllib.request
import http.cookiejar

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:5000"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. login page + csrf
r = op.open(BASE + "/login")
html = r.read().decode("utf-8")
m = re.search(r'name="csrf_token" value="([^"]+)"', html)
token = m.group(1) if m else ""
print("1) GET /login:", r.status, "| brand baisón:", "baisón" in html)

# 2. login
data = f"username=admin&password=admin123&csrf_token={token}".encode()
r = op.open(BASE + "/login", data)
print("2) POST /login →", r.status, r.url)

# 3. dashboard
r = op.open(BASE + "/")
html = r.read().decode("utf-8")
print("3) GET /:", r.status, "| dashboard ok:", "Заявки" in html or "заяв" in html.lower())

# 4. публичная форма (без логина)
r = op.open(BASE + "/lead?source=tiktok")
print("4) GET /lead?source=tiktok:", r.status)
data = "name=Проверка+PG&phone=8%20999%20000-11-22&source=tiktok&comment=котёл".encode()
req = urllib.request.Request(BASE + "/lead?source=tiktok", data=data,
                             method="POST")
try:
    r = op.open(req)
    print("5) POST /lead →", r.status, r.url)
except urllib.error.HTTPError as e:
    print("5) POST /lead → HTTPError", e.code)
