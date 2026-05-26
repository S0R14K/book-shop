import math

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from ..db import get_db
from ..services.open_library import search_books_with_status

shop_bp = Blueprint('shop', __name__)


BOOK_SELECT = """
    SELECT
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
    FROM books
    LEFT JOIN categories ON categories.id = books.category_id
"""


@shop_bp.route('/')
def home():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        f"""
        {BOOK_SELECT}
        WHERE books.is_active = 1
        ORDER BY books.featured DESC, books.id ASC
        LIMIT 4
        """
    )
    featured_books = cur.fetchall()

    cur.execute(
        f"""
        {BOOK_SELECT}
        WHERE books.is_active = 1
        ORDER BY books.id DESC
        LIMIT 4
        """
    )
    new_arrivals = cur.fetchall()

    categories = _get_categories(cur)
    wishlist_book_ids = _wishlist_book_ids(cur)
    conn.close()

    return render_template(
        'index.html',
        featured_books=featured_books,
        new_arrivals=new_arrivals,
        categories=categories,
        wishlist_book_ids=wishlist_book_ids,
    )


@shop_bp.route('/books')
def books():
    page = max(_parse_int(request.args.get("page", "1"), 1), 1)
    per_page = 12
    filters = {
        "q": request.args.get('q', '').strip(),
        "category": request.args.get('category', '').strip(),
        "min_price": request.args.get('min_price', '').strip(),
        "max_price": request.args.get('max_price', '').strip(),
        "sort": request.args.get('sort', 'title_asc').strip(),
    }

    where_clauses = ["books.is_active = 1"]
    params = []

    if filters["q"]:
        search_term = f"%{filters['q']}%"
        where_clauses.append(
            "(books.title LIKE ? OR books.author LIKE ? OR COALESCE(categories.name, books.category) LIKE ?)"
        )
        params.extend([search_term, search_term, search_term])

    if filters["category"]:
        where_clauses.append("COALESCE(categories.name, books.category) = ?")
        params.append(filters["category"])

    min_price = _parse_price(filters["min_price"])
    if min_price is not None:
        where_clauses.append("books.price_eur >= ?")
        params.append(min_price)

    max_price = _parse_price(filters["max_price"])
    if max_price is not None:
        where_clauses.append("books.price_eur <= ?")
        params.append(max_price)

    sort_sql = {
        "price_asc": "books.price_eur ASC",
        "price_desc": "books.price_eur DESC",
        "newest": "books.published_year DESC, books.id DESC",
        "title_asc": "books.title ASC",
    }.get(filters["sort"], "books.title ASC")

    count_query = """
        SELECT COUNT(*)
        FROM books
        LEFT JOIN categories ON categories.id = books.category_id
    """
    if where_clauses:
        count_query += " WHERE " + " AND ".join(where_clauses)

    query = BOOK_SELECT
    query += " WHERE " + " AND ".join(where_clauses)
    query += f" ORDER BY {sort_sql}"
    query += " LIMIT ? OFFSET ?"

    conn = get_db()
    cur = conn.cursor()

    cur.execute(count_query, params)
    total_results = cur.fetchone()[0]
    total_pages = max(1, math.ceil(total_results / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    cur.execute(query, [*params, per_page, offset])
    book_rows = cur.fetchall()
    categories = _get_categories(cur)
    wishlist_book_ids = _wishlist_book_ids(cur)
    conn.close()

    external_books = []
    external_status = None
    if filters["q"]:
        external_status = search_books_with_status(filters["q"], limit=4)
        external_books = external_status["results"]

    base_args = {key: value for key, value in filters.items() if value}
    base_args["sort"] = filters["sort"]
    pagination = {
        "page": page,
        "per_page": per_page,
        "total_results": total_results,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "start": 0 if total_results == 0 else offset + 1,
        "end": min(offset + len(book_rows), total_results),
        "base_args": base_args,
    }

    return render_template(
        'books.html',
        books=book_rows,
        categories=categories,
        filters=filters,
        pagination=pagination,
        external_books=external_books,
        external_status=external_status,
        wishlist_book_ids=wishlist_book_ids,
    )


@shop_bp.route('/books/<int:book_id>')
def legacy_book_detail(book_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT slug FROM books WHERE id = ? AND is_active = 1", (book_id,))
    book = cur.fetchone()
    conn.close()

    if not book:
        abort(404)
    return redirect(url_for("shop.book_detail", slug=book["slug"]), code=301)


@shop_bp.route('/books/<slug>')
def book_detail(slug):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"{BOOK_SELECT} WHERE books.slug = ? AND books.is_active = 1", (slug,))
    book = cur.fetchone()

    if not book:
        conn.close()
        abort(404)

    cur.execute(
        f"""
        {BOOK_SELECT}
        WHERE COALESCE(categories.name, books.category) = ?
          AND books.id != ?
          AND books.is_active = 1
        ORDER BY books.title ASC
        LIMIT 4
        """,
        (book["category"], book["id"]),
    )
    related_books = cur.fetchall()
    wishlist_book_ids = _wishlist_book_ids(cur)
    conn.close()

    return render_template(
        'book_detail.html',
        book=book,
        related_books=related_books,
        wishlist_book_ids=wishlist_book_ids,
    )


@shop_bp.route('/about')
def about():
    return render_template('about.html')


def _parse_price(value):
    if not value:
        return None
    try:
        price = float(value)
    except ValueError:
        return None
    return price if price >= 0 else None


def _parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_categories(cur):
    cur.execute(
        """
        SELECT categories.name, COUNT(books.id) AS book_count
        FROM categories
        LEFT JOIN books ON books.category_id = categories.id AND books.is_active = 1
        GROUP BY categories.id, categories.name
        ORDER BY categories.name
        """
    )
    return cur.fetchall()


def _wishlist_book_ids(cur):
    if not session.get("user_id"):
        return set()
    cur.execute(
        "SELECT book_id FROM wishlist_items WHERE user_id = ?",
        (session["user_id"],),
    )
    return {row["book_id"] for row in cur.fetchall()}
