from flask import Blueprint, jsonify, request
import requests

from ..services.open_library import fetch_enrichment, search_books_with_status

api_bp = Blueprint('api_bp', __name__)


@api_bp.route('/api/convert')
def convert():
    target = request.args.get('to', 'USD').upper()

    try:
        amount = float(request.args.get('amount', 0))
    except ValueError:
        return jsonify({"error": "Amount must be a number."}), 400

    try:
        response = requests.get("https://open.er-api.com/v6/latest/EUR", timeout=4)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return jsonify({"error": "Currency service unavailable."}), 503

    if "rates" not in data or target not in data["rates"]:
        return jsonify({"error": "Currency data unavailable."}), 400

    rate = data["rates"][target]
    converted_amount = amount * rate

    return jsonify({
        "rate": round(rate, 4),
        "total_converted": round(converted_amount, 2),
        "to": target,
    })


@api_bp.route('/api/open-library/search')
def open_library_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})

    try:
        limit = int(request.args.get("limit", 5))
    except ValueError:
        limit = 5

    status = search_books_with_status(query, limit=limit)
    http_status = 200 if status["results"] else 503

    return jsonify({
        "source": status["provider"],
        "cached": status["cached"],
        "stale": status["stale"],
        "status": status["source"],
        "error": status["error"],
        "results": status["results"],
    }), http_status


@api_bp.route('/api/book-enrichment')
def book_enrichment():
    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400

    book = fetch_enrichment(title, author)
    if not book:
        return jsonify({
            "error": "No external metadata match found right now.",
            "book": None,
        }), 404

    return jsonify({
        "error": "",
        "book": book,
    })
