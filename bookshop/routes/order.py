from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_db

order_bp = Blueprint('order_bp', __name__)

PAYMENT_METHODS = {
    "card": "Credit Card",
    "paypal": "PayPal",
    "cash": "Cash on Delivery",
}


@order_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in before checkout.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    db = get_db()
    cur = db.cursor()
    items = _cart_items(cur, user_id)
    total_eur = round(sum(item["price_eur"] * item["quantity"] for item in items), 2)

    if not items:
        db.close()
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart_bp.view_cart"))

    if request.method == "POST":
        form_data = {
            "name": request.form.get("name", "").strip(),
            "address": request.form.get("address", "").strip(),
            "city": request.form.get("city", "").strip(),
            "payment": request.form.get("payment", "card").strip(),
        }

        errors = _validate_checkout(form_data)
        stock_error = next((item for item in items if item["quantity"] > item["stock"]), None)
        if stock_error:
            errors.append(f"Only {stock_error['stock']} copies of {stock_error['title']} are available.")

        if errors:
            for error in errors:
                flash(error, "error")
            db.close()
            return render_template(
                "checkout.html",
                items=items,
                total=total_eur,
                payment_methods=PAYMENT_METHODS,
                form_data=form_data,
            )

        cur.execute(
            """
            INSERT INTO orders (
                user_id, total_eur, status, customer_name,
                shipping_address, city, payment_method
            )
            VALUES (?, ?, 'processing', ?, ?, ?, ?)
            """,
            (
                user_id,
                total_eur,
                form_data["name"],
                form_data["address"],
                form_data["city"],
                PAYMENT_METHODS[form_data["payment"]],
            ),
        )
        order_id = cur.lastrowid

        for item in items:
            cur.execute(
                """
                INSERT INTO order_items (order_id, book_id, quantity, price_eur)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, item["book_id"], item["quantity"], item["price_eur"]),
            )
            cur.execute(
                """
                UPDATE books
                SET stock = CASE
                    WHEN stock >= ? THEN stock - ?
                    ELSE 0
                END
                WHERE id = ?
                """,
                (item["quantity"], item["quantity"], item["book_id"]),
            )

        cur.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        db.commit()
        db.close()

        flash("Order placed successfully.", "success")
        return redirect(url_for("order_bp.confirmation", order_id=order_id))

    db.close()
    return render_template(
        "checkout.html",
        items=items,
        total=total_eur,
        payment_methods=PAYMENT_METHODS,
        form_data={},
    )


@order_bp.route("/order/<int:order_id>")
def confirmation(order_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login", next=request.path))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
    order = cur.fetchone()
    db.close()

    if not order:
        return render_template("errors/404.html"), 404

    return render_template("confirmation.html", order=order)


@order_bp.route("/orders")
def order_history():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to view your orders.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, total_eur, created_at, status
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )

    orders = cur.fetchall()
    db.close()
    return render_template("orders.html", orders=orders)


@order_bp.route("/order/details/<int:order_id>")
def order_details(order_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login", next=request.path))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
    order = cur.fetchone()

    if not order:
        db.close()
        return render_template("errors/404.html"), 404

    cur.execute(
        """
        SELECT books.title, books.author, order_items.quantity, order_items.price_eur
        FROM order_items
        JOIN books ON books.id = order_items.book_id
        WHERE order_items.order_id = ?
        ORDER BY books.title
        """,
        (order_id,),
    )
    items = cur.fetchall()
    db.close()

    return render_template("order_details.html", order=order, items=items)


def _cart_items(cur, user_id):
    cur.execute(
        """
        SELECT
            cart_items.book_id,
            cart_items.quantity,
            books.title,
            books.author,
            books.price_eur,
            books.stock,
            books.slug,
            books.cover_image
        FROM cart_items
        JOIN books ON books.id = cart_items.book_id
        WHERE cart_items.user_id = ?
        ORDER BY books.title
        """,
        (user_id,),
    )
    return cur.fetchall()


def _validate_checkout(form_data):
    errors = []
    if len(form_data["name"]) < 2:
        errors.append("Name must be at least 2 characters long.")
    if len(form_data["address"]) < 5:
        errors.append("Address must be at least 5 characters long.")
    if len(form_data["city"]) < 2:
        errors.append("City must be at least 2 characters long.")
    if form_data["payment"] not in PAYMENT_METHODS:
        errors.append("Please choose a valid payment method.")
    return errors
