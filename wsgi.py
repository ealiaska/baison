import app._env  # noqa: F401  — подхватывает .env до создания приложения
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Разработcкий режим: debug + автоперезагрузка.
    # Продакшен:  py -m waitress --listen=127.0.0.1:5000 --threads=8 wsgi:app
    app.run(host="127.0.0.1", port=5000, debug=True)
