from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_db

account_bp = Blueprint("account", __name__)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


@account_bp.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, email, is_admin, created_at FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    order_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wishlist_items WHERE user_id = ?", (user_id,))
    wishlist_count = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE user_id = ?", (user_id,))
    cart_count = cur.fetchone()[0] or 0
    db.close()

    return render_template(
        "profile.html",
        user=user,
        order_count=order_count,
        wishlist_count=wishlist_count,
        cart_count=cart_count,
    )


@account_bp.route("/wishlist")
@login_required
def wishlist():
    user_id = session["user_id"]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            wishlist_items.id AS wishlist_item_id,
            books.id,
            books.title,
            books.author,
            books.description,
            books.price_eur,
            books.stock,
            books.cover_image,
            books.slug,
            books.isbn,
            books.published_year,
            books.featured,
            books.is_active,
            COALESCE(categories.name, books.category, 'General') AS category
        FROM wishlist_items
        JOIN books ON books.id = wishlist_items.book_id
        LEFT JOIN categories ON categories.id = books.category_id
        WHERE wishlist_items.user_id = ?
          AND books.is_active = 1
        ORDER BY wishlist_items.created_at DESC
        """,
        (user_id,),
    )
    books = cur.fetchall()
    db.close()
    return render_template("wishlist.html", books=books, wishlist_book_ids={book["id"] for book in books})


@account_bp.route("/wishlist/add/<int:book_id>", methods=["POST"])
@login_required
def add_to_wishlist(book_id):
    user_id = session["user_id"]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM books WHERE id = ? AND is_active = 1", (book_id,))
    if not cur.fetchone():
        db.close()
        flash("Book not found.", "error")
        return redirect(url_for("shop.books"))

    cur.execute(
        "INSERT OR IGNORE INTO wishlist_items (user_id, book_id) VALUES (?, ?)",
        (user_id, book_id),
    )
    db.commit()
    db.close()
    flash("Book saved to your wishlist.", "success")
    return redirect(request.referrer or url_for("account.wishlist"))


@account_bp.route("/wishlist/remove/<int:book_id>", methods=["POST"])
@login_required
def remove_from_wishlist(book_id):
    user_id = session["user_id"]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM wishlist_items WHERE user_id = ? AND book_id = ?",
        (user_id, book_id),
    )
    db.commit()
    db.close()
    flash("Book removed from your wishlist.", "success")
    return redirect(request.referrer or url_for("account.wishlist"))
