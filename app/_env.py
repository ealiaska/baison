"""Минимальный загрузчик .env без внешних зависимостей.

Подхватывает переменные из .env в корне проекта (если файла нет — тихо).
Не перезаписывает уже установленные переменные окружения (они важнее).
"""
import os

_ENV_LOADED = False


def load_dotenv(path=None):
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()
