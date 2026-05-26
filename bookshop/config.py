import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    DATABASE = os.path.join(BASE_DIR, "instance", "bookshop.sqlite")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    OPEN_LIBRARY_USER_AGENT = os.environ.get(
        "OPEN_LIBRARY_USER_AGENT",
        "BookNestStudentProject/1.0 (coursework@example.com)",
    )
