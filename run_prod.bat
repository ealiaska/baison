@echo off
rem baisón — production-запуск (waitress, Windows)
rem На Linux-хостинге: gunicorn -b 0.0.0.0:5000 --workers 2 "wsgi:app"
cd /d %~dp0
py -m waitress --listen=127.0.0.1:5000 --threads=8 wsgi:app
