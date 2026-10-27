import re
import requests

s = requests.Session()
r = s.get("http://127.0.0.1:5000/login")
token = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post("http://127.0.0.1:5000/login",
           data={"username": "admin", "password": "admin123", "csrf_token": token})
print("login post:", r.status_code, r.headers.get("Location"))

r = s.get("http://127.0.0.1:5000/")
print("dashboard:", r.status_code, "baisón" in r.text)

r = s.get("http://127.0.0.1:5000/crm/leads")
token = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post("http://127.0.0.1:5000/crm/leads/add",
           data={"name": "Тест", "phone": "123", "source": "авито", "csrf_token": token},
           allow_redirects=False)
print("lead add:", r.status_code, r.headers.get("Location"))
