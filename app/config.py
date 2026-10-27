import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///teplodom.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Токен для публичного вебхука приёма лидов (Instagram/TikTok-агрегаторы, CRM)
    WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "")

    # Автопилот заявок: автозаполнение пустых полей из текста,
    # автоназначение менеджера и автозадача на звонок
    AUTOPILOT_ENABLED = os.environ.get("AUTOPILOT", "1") != "0"
    AUTOPILOT_CREATE_TASK = os.environ.get("AUTOPILOT_TASK", "1") != "0"

    # Instagram DM webhook (Meta Instagram Messaging API)
    # developers.facebook.com → ваше приложение → Webhooks → Instagram
    IG_VERIFY_TOKEN = os.environ.get("IG_VERIFY_TOKEN", "")   # токен проверки Callback URL
    IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")   # token с instagram_manage_messages
    IG_USER_ID = os.environ.get("IG_USER_ID", "")             # IG user id бизнес-аккаунта
    IG_GRAPH_URL = os.environ.get("IG_GRAPH_URL", "https://graph.facebook.com/v23.0")
    IG_AUTO_REPLY = os.environ.get("IG_AUTO_REPLY", "1") != "0"  # приветственный автоответ новому клиенту
    IG_REPLY_TEXT = os.environ.get(
        "IG_REPLY_TEXT",
        "Здравствуйте! Спасибо за обращение. Напишите, пожалуйста, ваш телефон "
        "— менеджер свяжется и всё посчитает.",
    )

    # amoCRM (Настройки → Настройки → API)
    AMOCRM_URL = os.environ.get("AMOCRM_URL", "")  # https://company.amocrm.ru
    AMOCRM_KEY = os.environ.get("AMOCRM_KEY", "")
    AMOCRM_SECRET = os.environ.get("AMOCRM_SECRET", "")
    AMOCRM_PIPELINE_ID = os.environ.get("AMOCRM_PIPELINE_ID", "")

    # 1С REST (REST Web Services в 1С)
    ONES_URL = os.environ.get("ONES_URL", "")  # https://server:port/bs/...
    ONES_USER = os.environ.get("ONES_USER", "")
    ONES_PASS = os.environ.get("ONES_PASS", "")
    ONES_CATALOG_PATH = os.environ.get("ONES_CATALOG_PATH", "/rest/tp/v2/nomenklatura")
    ONES_STOCKS_PATH = os.environ.get("ONES_STOCKS_PATH", "/rest/tp/v2/ozh")
    ONES_DOC_PATH = os.environ.get("ONES_DOC_PATH", "/rest/tp/v2/schet-klientu")

    YEAR = None  # используется генератором номеров (переопределяется в тестах)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
