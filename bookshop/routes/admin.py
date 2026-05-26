from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_db
from ..services.open_library import isbn_cover_url
from ..utils import slugify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ORDER_STATUSES = ("pending", "processing", "shipped", "completed")


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in as an admin.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        if not session.get("is_admin"):
            flash("You do not have permission to access the admin area.", "error")
            return redirect(url_for("shop.home"))
        return view(*args, **kwargs)

    return wrapped_view


@admin_bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    cur = db.cursor()
    counts = {}
    for table in ("users", "books", "categories", "orders"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]

    cur.execute(
        """
        SELECT orders.id, orders.total_eur, orders.status, orders.created_at, users.email
        FROM orders
        JOIN users ON users.id = orders.user_id
        ORDER BY orders.created_at DESC
        LIMIT 6
        """
    )
    recent_orders = cur.fetchall()
    db.close()
    return render_template("admin/dashboard.html", counts=counts, recent_orders=recent_orders)


@admin_bp.route("/books")
@admin_required
def books():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            books.id,
            books.title,
            books.author,
            books.price_eur,
            books.stock,
            books.slug,
            books.featured,
            books.is_active,
            COALESCE(categories.name, books.category, 'General') AS category
        FROM books
        LEFT JOIN categories ON categories.id = books.category_id
        ORDER BY books.is_active DESC, books.title ASC
        """
    )
    books = cur.fetchall()
    db.close()
    return render_template("admin/books.html", books=books)


@admin_bp.route("/books/new", methods=["GET", "POST"])
@admin_required
def new_book():
    db = get_db()
    cur = db.cursor()
    categories = _categories(cur)

    if request.method == "POST":
        form_data = _book_form_data()
        errors = _validate_book(form_data)
        category = _category_by_id(cur, form_data["category_id"]) if not errors else None
        if not errors and not category:
            errors["category_id"] = "Choose an existing category."

        if errors:
            db.close()
            return render_template(
                "admin/book_form.html",
                mode="new",
                categories=categories,
                book=form_data,
                errors=errors,
            )

        cover_image = form_data["cover_image"] or isbn_cover_url(form_data["isbn"])
        cur.execute(
            """
            INSERT INTO books (
                title, author, description, price_eur, stock, cover_image,
                category, category_id, slug, isbn, published_year, featured, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                form_data["title"],
                form_data["author"],
                form_data["description"],
                form_data["price_eur"],
                form_data["stock"],
                cover_image,
                category["name"],
                form_data["category_id"],
                _unique_slug(cur, form_data["title"]),
                form_data["isbn"],
                form_data["published_year"],
                1 if form_data["featured"] else 0,
            ),
        )
        db.commit()
        db.close()
        flash("Book created.", "success")
        return redirect(url_for("admin.books"))

    db.close()
    return render_template("admin/book_form.html", mode="new", categories=categories, book={}, errors={})


@admin_bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_book(book_id):
    db = get_db()
    cur = db.cursor()
    categories = _categories(cur)
    cur.execute("SELECT * FROM books WHERE id = ?", (book_id,))
    book = cur.fetchone()

    if not book:
        db.close()
        flash("Book not found.", "error")
        return redirect(url_for("admin.books"))

    if request.method == "POST":
        form_data = _book_form_data()
        errors = _validate_book(form_data)
        category = _category_by_id(cur, form_data["category_id"]) if not errors else None
        if not errors and not category:
            errors["category_id"] = "Choose an existing category."

        if errors:
            db.close()
            return render_template(
                "admin/book_form.html",
                mode="edit",
                categories=categories,
                book={**dict(book), **form_data},
                errors=errors,
            )

        cover_image = form_data["cover_image"] or isbn_cover_url(form_data["isbn"])
        cur.execute(
            """
            UPDATE books
            SET title = ?, author = ?, description = ?, price_eur = ?, stock = ?,
                cover_image = ?, category = ?, category_id = ?, slug = ?, isbn = ?,
                published_year = ?, featured = ?
            WHERE id = ?
            """,
            (
                form_data["title"],
                form_data["author"],
                form_data["description"],
                form_data["price_eur"],
                form_data["stock"],
                cover_image,
                category["name"],
                form_data["category_id"],
                _unique_slug(cur, form_data["title"], book_id),
                form_data["isbn"],
                form_data["published_year"],
                1 if form_data["featured"] else 0,
                book_id,
            ),
        )
        db.commit()
        db.close()
        flash("Book updated.", "success")
        return redirect(url_for("admin.books"))

    db.close()
    return render_template("admin/book_form.html", mode="edit", categories=categories, book=book, errors={})


@admin_bp.route("/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def delete_book(book_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE books SET is_active = 0, featured = 0 WHERE id = ?", (book_id,))
    db.commit()
    db.close()
    flash("Book removed from the public catalog.", "success")
    return redirect(url_for("admin.books"))


@admin_bp.route("/books/<int:book_id>/restore", methods=["POST"])
@admin_required
def restore_book(book_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE books SET is_active = 1 WHERE id = ?", (book_id,))
    db.commit()
    db.close()
    flash("Book restored to the catalog.", "success")
    return redirect(url_for("admin.books"))


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if len(name) < 2:
            flash("Category name must be at least 2 characters.", "error")
        else:
            cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
            db.commit()
            flash("Category saved.", "success")

    cur.execute(
        """
        SELECT categories.id, categories.name, COUNT(books.id) AS book_count
        FROM categories
        LEFT JOIN books ON books.category_id = categories.id
        GROUP BY categories.id, categories.name
        ORDER BY categories.name
        """
    )
    categories = cur.fetchall()
    db.close()
    return render_template("admin/categories.html", categories=categories)


@admin_bp.route("/categories/<int:category_id>/edit", methods=["POST"])
@admin_required
def edit_category(category_id):
    name = request.form.get("name", "").strip()
    if len(name) < 2:
        flash("Category name must be at least 2 characters.", "error")
        return redirect(url_for("admin.categories"))

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
    cur.execute("UPDATE books SET category = ? WHERE category_id = ?", (name, category_id))
    db.commit()
    db.close()
    flash("Category updated.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM books WHERE category_id = ?", (category_id,))
    count = cur.fetchone()[0]
    if count:
        flash("Category cannot be deleted while books use it.", "error")
    else:
        cur.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        db.commit()
        flash("Category deleted.", "success")
    db.close()
    return redirect(url_for("admin.categories"))


@admin_bp.route("/orders")
@admin_required
def orders():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT orders.*, users.email
        FROM orders
        JOIN users ON users.id = orders.user_id
        ORDER BY orders.created_at DESC
        """
    )
    orders = cur.fetchall()
    db.close()
    return render_template("admin/orders.html", orders=orders, statuses=ORDER_STATUSES)


@admin_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status = request.form.get("status", "").strip()
    if status not in ORDER_STATUSES:
        flash("Invalid order status.", "error")
        return redirect(url_for("admin.orders"))

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    db.commit()
    db.close()
    flash("Order status updated.", "success")
    return redirect(url_for("admin.orders"))


def _book_form_data():
    return {
        "title": request.form.get("title", "").strip(),
        "author": request.form.get("author", "").strip(),
        "description": request.form.get("description", "").strip(),
        "price_eur": _number(request.form.get("price_eur")),
        "stock": _integer(request.form.get("stock")),
        "cover_image": request.form.get("cover_image", "").strip(),
        "category_id": _integer(request.form.get("category_id")),
        "isbn": request.form.get("isbn", "").strip(),
        "published_year": _integer(request.form.get("published_year")),
        "featured": request.form.get("featured") == "1",
    }


def _validate_book(data):
    errors = {}
    if len(data["title"]) < 2:
        errors["title"] = "Title is required."
    if len(data["author"]) < 2:
        errors["author"] = "Author is required."
    if data["price_eur"] is None or data["price_eur"] <= 0:
        errors["price_eur"] = "Price must be greater than 0."
    if data["stock"] is None or data["stock"] < 0:
        errors["stock"] = "Stock must be 0 or higher."
    if not data["category_id"]:
        errors["category_id"] = "Choose a category."
    if data["published_year"] is not None and not (1000 <= data["published_year"] <= 2100):
        errors["published_year"] = "Use a realistic publication year."
    return errors


def _categories(cur):
    cur.execute("SELECT id, name FROM categories ORDER BY name")
    return cur.fetchall()


def _category_by_id(cur, category_id):
    cur.execute("SELECT id, name FROM categories WHERE id = ?", (category_id,))
    return cur.fetchone()


def _unique_slug(cur, title, book_id=None):
    base_slug = slugify(title)
    candidate = base_slug
    suffix = 2
    while True:
        if book_id:
            cur.execute("SELECT id FROM books WHERE slug = ? AND id != ?", (candidate, book_id))
        else:
            cur.execute("SELECT id FROM books WHERE slug = ?", (candidate,))
        if not cur.fetchone():
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _number(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _integer(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
