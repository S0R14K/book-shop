import os

from flask import Flask, render_template, request, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

from .config import Config
from .db import get_db
from .sample_data import DEFAULT_BOOKS
from .services.open_library import isbn_cover_url
from .utils import slugify

from .routes.api_routes import api_bp
from .routes.admin import admin_bp
from .routes.account import account_bp
from .routes.auth import auth_bp
from .routes.cart_routes import cart_bp
from .routes.order import order_bp
from .routes.shop import shop_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    csrf = CSRFProtect()
    csrf.init_app(app)

    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_user_state():
        cart_count = 0
        wishlist_count = 0
        if session.get("user_id"):
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE user_id = ?",
                (session["user_id"],),
            )
            cart_count = cur.fetchone()[0] or 0
            cur.execute(
                "SELECT COUNT(*) FROM wishlist_items WHERE user_id = ?",
                (session["user_id"],),
            )
            wishlist_count = cur.fetchone()[0] or 0
            db.close()
        return {
            "cart_count": cart_count,
            "wishlist_count": wishlist_count,
            "current_endpoint": request.endpoint or "",
            "is_admin": bool(session.get("is_admin")),
        }

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500

    return app


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            description TEXT,
            price_eur REAL NOT NULL,
            stock INTEGER NOT NULL,
            cover_image TEXT,
            category TEXT,
            category_id INTEGER,
            slug TEXT,
            isbn TEXT,
            openlibrary_key TEXT,
            published_year INTEGER,
            featured INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, book_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_eur REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            customer_name TEXT,
            shipping_address TEXT,
            city TEXT,
            payment_method TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            quantity INTEGER,
            price_eur REAL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE NOT NULL,
            provider TEXT NOT NULL,
            response_json TEXT NOT NULL,
            cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    _ensure_column(cur, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cur, "books", "category_id", "INTEGER")
    _ensure_column(cur, "books", "slug", "TEXT")
    _ensure_column(cur, "books", "isbn", "TEXT")
    _ensure_column(cur, "books", "openlibrary_key", "TEXT")
    _ensure_column(cur, "books", "published_year", "INTEGER")
    _ensure_column(cur, "books", "featured", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cur, "books", "is_active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(cur, "orders", "status", "TEXT DEFAULT 'pending'")
    _ensure_column(cur, "orders", "customer_name", "TEXT")
    _ensure_column(cur, "orders", "shipping_address", "TEXT")
    _ensure_column(cur, "orders", "city", "TEXT")
    _ensure_column(cur, "orders", "payment_method", "TEXT")

    _deduplicate_books(cur)
    _seed_default_books(cur)
    _sync_categories(cur)
    _backfill_book_slugs(cur)
    _backfill_book_covers(cur)
    _ensure_default_admin(cur)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_category_id ON books(category_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_price ON books(price_eur)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_is_active ON books(is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cart_user_id ON cart_items(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_user_id ON wishlist_items(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_books_slug ON books(slug)")

    conn.commit()
    conn.close()


def _ensure_column(cur, table, column, definition):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row["name"] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_default_books(cur):
    for book in DEFAULT_BOOKS:
        cur.execute(
            "SELECT id FROM books WHERE lower(trim(title)) = lower(trim(?)) AND lower(trim(author)) = lower(trim(?))",
            (book["title"], book["author"]),
        )
        if cur.fetchone():
            continue

        category_id = _get_or_create_category(cur, book["category"])
        cur.execute(
            """
            INSERT INTO books (
                title, author, description, price_eur, stock, cover_image,
                category, category_id, slug, isbn, published_year, featured
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book["title"],
                book["author"],
                book["description"],
                book["price_eur"],
                book["stock"],
                isbn_cover_url(book.get("isbn")),
                book["category"],
                category_id,
                _unique_slug(cur, book["title"]),
                book.get("isbn"),
                book.get("published_year"),
                book.get("featured", 0),
            ),
        )


def _deduplicate_books(cur):
    cur.execute(
        """
        SELECT
            lower(trim(title)) AS normalized_title,
            lower(trim(author)) AS normalized_author,
            MIN(id) AS keep_id,
            GROUP_CONCAT(id) AS ids,
            COUNT(*) AS duplicate_count
        FROM books
        GROUP BY lower(trim(title)), lower(trim(author))
        HAVING COUNT(*) > 1
        """
    )
    duplicate_groups = cur.fetchall()

    for group in duplicate_groups:
        keep_id = group["keep_id"]
        duplicate_ids = [
            int(book_id)
            for book_id in group["ids"].split(",")
            if int(book_id) != keep_id
        ]

        for duplicate_id in duplicate_ids:
            cur.execute(
                "UPDATE cart_items SET book_id = ? WHERE book_id = ?",
                (keep_id, duplicate_id),
            )
            cur.execute(
                "UPDATE order_items SET book_id = ? WHERE book_id = ?",
                (keep_id, duplicate_id),
            )
            cur.execute("DELETE FROM books WHERE id = ?", (duplicate_id,))


def _sync_categories(cur):
    cur.execute("SELECT id, category FROM books WHERE category_id IS NULL")
    for book in cur.fetchall():
        category_id = _get_or_create_category(cur, book["category"] or "General")
        cur.execute(
            "UPDATE books SET category_id = ?, category = ? WHERE id = ?",
            (category_id, book["category"] or "General", book["id"]),
        )


def _backfill_book_slugs(cur):
    cur.execute("SELECT id, title, slug FROM books")
    for book in cur.fetchall():
        if not book["slug"]:
            cur.execute(
                "UPDATE books SET slug = ? WHERE id = ?",
                (_unique_slug(cur, book["title"], book["id"]), book["id"]),
            )


def _backfill_book_covers(cur):
    cur.execute("SELECT id, isbn, cover_image FROM books")
    for book in cur.fetchall():
        if book["isbn"] and not book["cover_image"]:
            cur.execute(
                "UPDATE books SET cover_image = ? WHERE id = ?",
                (isbn_cover_url(book["isbn"]), book["id"]),
            )


def _get_or_create_category(cur, name):
    category_name = (name or "General").strip() or "General"
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (category_name,))
    cur.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
    return cur.fetchone()["id"]


def _ensure_default_admin(cur):
    admin_email = os.environ.get("BOOKNEST_ADMIN_EMAIL", "admin@booknest.test").lower()
    admin_password = os.environ.get("BOOKNEST_ADMIN_PASSWORD", "Admin12345")

    cur.execute("SELECT id, is_admin FROM users WHERE email = ?", (admin_email,))
    admin = cur.fetchone()
    if admin:
        if not admin["is_admin"]:
            cur.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (admin["id"],))
        return

    cur.execute(
        "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
        (admin_email, generate_password_hash(admin_password)),
    )


def _unique_slug(cur, title, book_id=None):
    base_slug = slugify(title)
    candidate = base_slug
    suffix = 2

    while True:
        if book_id:
            cur.execute(
                "SELECT id FROM books WHERE slug = ? AND id != ?",
                (candidate, book_id),
            )
        else:
            cur.execute("SELECT id FROM books WHERE slug = ?", (candidate,))
        if not cur.fetchone():
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
