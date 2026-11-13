import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except Exception:  # python-dotenv is optional
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", os.path.join(ROOT, "accesslearn.db"))
