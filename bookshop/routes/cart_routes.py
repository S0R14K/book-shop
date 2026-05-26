from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_db

cart_bp = Blueprint('cart_bp', __name__)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please log in to continue.", "warning")
            return redirect(url_for('auth.login', next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


@cart_bp.route('/cart')
@login_required
def view_cart():
    user_id = session['user_id']

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            cart_items.id,
            cart_items.book_id,
            cart_items.quantity,
            books.title,
            books.author,
            books.price_eur,
            books.stock,
            books.cover_image,
            books.slug,
            COALESCE(categories.name, books.category, 'General') AS category
        FROM cart_items
        JOIN books ON books.id = cart_items.book_id
        LEFT JOIN categories ON categories.id = books.category_id
        WHERE cart_items.user_id = ?
        ORDER BY books.title
        """,
        (user_id,),
    )

    items = cur.fetchall()
    conn.close()

    total = round(sum(item['price_eur'] * item['quantity'] for item in items), 2)
    return render_template('cart.html', items=items, total=total)


@cart_bp.route('/cart/add/<int:book_id>', methods=['POST'])
@login_required
def add_to_cart(book_id):
    quantity = _parse_quantity(request.form.get("quantity", "1"))
    user_id = session['user_id']

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, stock FROM books WHERE id = ?", (book_id,))
    book = cur.fetchone()
    if not book:
        conn.close()
        flash("Book not found.", "error")
        return redirect(url_for('shop.books'))

    if book["stock"] <= 0:
        conn.close()
        flash("This book is currently out of stock.", "error")
        return redirect(request.referrer or url_for('shop.books'))

    cur.execute(
        "SELECT id, quantity FROM cart_items WHERE user_id = ? AND book_id = ?",
        (user_id, book_id),
    )
    existing = cur.fetchone()

    if existing:
        new_quantity = min(existing["quantity"] + quantity, book["stock"])
        cur.execute(
            "UPDATE cart_items SET quantity = ? WHERE id = ? AND user_id = ?",
            (new_quantity, existing['id'], user_id),
        )
    else:
        cur.execute(
            "INSERT INTO cart_items (user_id, book_id, quantity) VALUES (?, ?, ?)",
            (user_id, book_id, min(quantity, book["stock"])),
        )

    conn.commit()
    conn.close()

    flash("Book added to cart.", "success")
    return redirect(request.referrer or url_for('cart_bp.view_cart'))


@cart_bp.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart_item(item_id):
    quantity = _parse_quantity(request.form.get("quantity", "1"))
    user_id = session['user_id']

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cart_items.id, books.stock
        FROM cart_items
        JOIN books ON books.id = cart_items.book_id
        WHERE cart_items.id = ? AND cart_items.user_id = ?
        """,
        (item_id, user_id),
    )
    item = cur.fetchone()

    if not item:
        conn.close()
        flash("Cart item not found.", "error")
        return redirect(url_for('cart_bp.view_cart'))

    cur.execute(
        "UPDATE cart_items SET quantity = ? WHERE id = ? AND user_id = ?",
        (min(quantity, item["stock"]), item_id, user_id),
    )
    conn.commit()
    conn.close()

    flash("Cart updated.", "success")
    return redirect(url_for('cart_bp.view_cart'))


@cart_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    user_id = session['user_id']

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cart_items WHERE id = ? AND user_id = ?",
        (item_id, user_id),
    )
    conn.commit()
    conn.close()

    flash("Item removed from cart.", "success")
    return redirect(url_for('cart_bp.view_cart'))


def _parse_quantity(value):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        quantity = 1
    return max(1, min(quantity, 99))
