import os
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    # pip install pymysql
    # SQLALCHEMY_DATABASE_URI = "mysql+pymysql://root:@localhost/ssssss"

    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///mydb.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "secret")
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=1440)  # session TTL

    # Server & Port
    PORT = int(os.environ.get("PORT", 3000))

    # Store configurations
    STORE_NAME = os.environ.get("STORE_NAME", "TechStore")
    STORE_TIMEZONE = os.environ.get("STORE_TIMEZONE", "Asia/Phnom_Penh")
    LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", 5))
    GRACE_PERIOD_HOURS = int(os.environ.get("GRACE_PERIOD_HOURS", 4))
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "True").lower() in ("true", "1", "yes")

    # Currency Engine (Authoritative KHR / USD presentation estimate)
    KHR_RATE = float(os.environ.get("KHR_RATE", 4000.0))

    # JWT Authentication
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", os.environ.get("SECRET_KEY", "jwt-secret-key-change-in-production"))

    # NBC Bakong KHQR Gateway Configuration
    BAKONG_TOKEN = os.environ.get("BAKONG_TOKEN", "")
    BAKONG_ACCOUNT_ID = os.environ.get("BAKONG_ACCOUNT_ID", "thoeung_sereymongkol@bkrt")
    BAKONG_MERCHANT_NAME = os.environ.get("BAKONG_MERCHANT_NAME", "TechStore")
    BAKONG_MERCHANT_CITY = os.environ.get("BAKONG_MERCHANT_CITY", "Phnom Penh")
    BAKONG_CURRENCY = os.environ.get("BAKONG_CURRENCY", "KHR")
    BAKONG_PHONE_NUMBER = os.environ.get("BAKONG_PHONE_NUMBER", "012345678")
    BAKONG_STORE_LABEL = os.environ.get("BAKONG_STORE_LABEL", "Cashier-01")
    BAKONG_TERMINAL_LABEL = os.environ.get("BAKONG_TERMINAL_LABEL", "POS-01")

    # Mail configurations (Optional)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")

    # Upload configurations
    UPLOAD_DIR = os.path.join("static", "images", "user")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # Telegram bot configurations (Orders / General)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "@SETEC_PP_SHOP")

    # Telegram security alert configurations (Rate limits / Attack monitoring)
    TELEGRAM_ALERT_BOT_TOKEN = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN", "")
    TELEGRAM_ALERT_CHAT_ID = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "@pp_shop_alert")

# Module-level shortcuts for convenience
PORT = Config.PORT
UPLOAD_DIR = Config.UPLOAD_DIR
ALLOWED_EXT = Config.ALLOWED_EXTENSIONS
TELEGRAM_BOT_TOKEN = Config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = Config.TELEGRAM_CHAT_ID
TELEGRAM_ALERT_BOT_TOKEN = Config.TELEGRAM_ALERT_BOT_TOKEN
TELEGRAM_ALERT_CHAT_ID = Config.TELEGRAM_ALERT_CHAT_ID
STORE_NAME = Config.STORE_NAME
STORE_TIMEZONE = Config.STORE_TIMEZONE
LOW_STOCK_THRESHOLD = Config.LOW_STOCK_THRESHOLD
GRACE_PERIOD_HOURS = Config.GRACE_PERIOD_HOURS
SCHEDULER_ENABLED = Config.SCHEDULER_ENABLED
KHR_RATE = Config.KHR_RATE
JWT_SECRET_KEY = Config.JWT_SECRET_KEY
BAKONG_TOKEN = Config.BAKONG_TOKEN
BAKONG_ACCOUNT_ID = Config.BAKONG_ACCOUNT_ID
BAKONG_MERCHANT_NAME = Config.BAKONG_MERCHANT_NAME
BAKONG_MERCHANT_CITY = Config.BAKONG_MERCHANT_CITY
BAKONG_CURRENCY = Config.BAKONG_CURRENCY
BAKONG_PHONE_NUMBER = Config.BAKONG_PHONE_NUMBER
BAKONG_STORE_LABEL = Config.BAKONG_STORE_LABEL
BAKONG_TERMINAL_LABEL = Config.BAKONG_TERMINAL_LABEL
