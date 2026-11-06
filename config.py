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

    # Store configurations
    STORE_NAME = os.environ.get("STORE_NAME", "TechStore")
    STORE_TIMEZONE = os.environ.get("STORE_TIMEZONE", "Asia/Phnom_Penh")
    LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", 5))
    GRACE_PERIOD_HOURS = int(os.environ.get("GRACE_PERIOD_HOURS", 4))
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "True").lower() in ("true", "1", "yes")

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
