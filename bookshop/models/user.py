from werkzeug.security import generate_password_hash, check_password_hash
from ..db import get_db

class User:

    @staticmethod
    def create(email, password):
        conn = get_db()
        cur = conn.cursor()

        password_hash = generate_password_hash(password)

        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", 
                    (email, password_hash))
        conn.commit()
        conn.close()

    @staticmethod
    def find_by_email(email):
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()

        conn.close()
        return user

    @staticmethod
    def check_password(stored_hash, password):
        return check_password_hash(stored_hash, password)
