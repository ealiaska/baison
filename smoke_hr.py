import re

from app import create_app

app = create_app()
c = app.test_client()
t = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
c.post("/login", data={"username": "admin", "password": "admin123", "csrf_token": t})
r = c.post("/hr/employees/add",
           data={"name": "Тест Тестов", "position": "монтажник", "shift_start": "09:00",
                 "csrf_token": t})
print("add employee:", r.status_code)
r = c.get("/hr/")
print("hr page:", r.status_code, "Тест Тестов" in r.text)
r = c.get("/hr")
print("hr redirect:", r.status_code, r.headers.get("Location"))
