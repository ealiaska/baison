"""Живой smoke: логин Aliaskar, отчёты, мобильный топбар, PDF-кнопка."""
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:5000"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

h = op.open(BASE + "/login", timeout=15).read().decode("utf-8", "ignore")
tok = re.search(r'name="csrf_token" value="([^"]+)"', h)
data = urllib.parse.urlencode({
    "username": "Aliaskar", "password": "Asd123456",
    "csrf_token": tok.group(1) if tok else ""}).encode()
r = op.open(BASE + "/login", data, timeout=15)
print("1) login:", r.status, r.url)

dash = op.open(BASE + "/", timeout=15).read().decode("utf-8", "ignore")
print("2) dashboard:", "baisón" in dash, "| topbar (mobile):", 'class="topbar"' in dash,
      "| burger:", "menu-btn" in dash)

rep = op.open(BASE + "/reports/", timeout=15).read().decode("utf-8", "ignore")
print("3) reports ok:", "Отчёты" in rep and "Выручка по менеджерам" in rep)

inv_list = op.open(BASE + "/sales/invoices", timeout=15).read().decode("utf-8", "ignore")
print("4) invoices page:", "Счета" in inv_list or "Счета" in inv_list)
