import json
from datetime import datetime, timezone

import requests
from flask import current_app

from ..db import get_db


OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_WORK_URL = "https://openlibrary.org{key}.json"
OPEN_LIBRARY_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
ISBN_COVER_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
GOOGLE_BOOKS_SEARCH_URL = "https://www.googleapis.com/books/v1/volumes"
CACHE_TTL_HOURS = 24


class BookApiError(Exception):
    pass


class OpenLibraryError(BookApiError):
    pass


def isbn_cover_url(isbn):
    if not isbn:
        return ""
    return ISBN_COVER_URL.format(isbn=isbn)


def search_books_with_status(query, limit=5):
    query = (query or "").strip()
    limit = max(1, min(int(limit), 10))
    if not query:
        return _status([], "none", cached=False)

    cache_key = _cache_key("search", query, limit)
    cached = _read_cache(cache_key, fresh_only=True)
    if cached:
        return _status(cached["results"], cached["provider"], cached=True, source="cache")

    errors = []
    for provider, fetcher in (
        ("Open Library", _search_open_library),
        ("Google Books", _search_google_books),
    ):
        try:
            results = fetcher(query, limit)
            if results:
                _write_cache(cache_key, provider, results)
                return _status(results, provider, cached=False, source="live")
            errors.append(f"{provider} returned no results")
        except BookApiError as exc:
            errors.append(str(exc))

    stale = _read_cache(cache_key, fresh_only=False)
    if stale:
        return _status(
            stale["results"],
            stale["provider"],
            cached=True,
            stale=True,
            source="stale-cache",
            error="Live book APIs are unavailable, so cached results are shown.",
        )

    return _status(
        [],
        "none",
        cached=False,
        source="unavailable",
        error="External book information is temporarily unavailable.",
        details=errors,
    )


def fetch_enrichment(title, author=""):
    title = (title or "").strip()
    author = (author or "").strip()
    queries = [
        " ".join(part for part in [title, author] if part).strip(),
        title,
        " ".join(part for part in [author, title] if part).strip(),
    ]

    status = None
    for query in dict.fromkeys(query for query in queries if query):
        status = search_books_with_status(query, limit=3)
        if status["results"]:
            break

    if not status or not status["results"]:
        return None

    book = _best_match(status["results"], title, author)
    book["api_provider"] = status["provider"]
    book["api_cached"] = status["cached"]
    book["api_error"] = status.get("error", "")

    if book.get("provider") == "Open Library" and book.get("key"):
        book["description"] = fetch_work_description(book["key"]) or book.get("description", "")
        book["source_url"] = f"https://openlibrary.org{book['key']}"
    elif book.get("provider") == "Google Books" and book.get("key"):
        book["source_url"] = f"https://books.google.com/books?id={book['key']}"

    return book


def _best_match(results, title, author):
    normalized_title = _normalize_text(title)
    normalized_author = _normalize_text(author)

    for result in results:
        result_title = _normalize_text(result.get("title", ""))
        if normalized_title and normalized_title == result_title:
            return result

    for result in results:
        result_authors = _normalize_text(result.get("authors", ""))
        if normalized_author and normalized_author in result_authors:
            return result

    for result in results:
        result_title = _normalize_text(result.get("title", ""))
        if normalized_title and normalized_title in result_title:
            return result
        if normalized_title and result_title in normalized_title:
            return result

    return results[0]


def fetch_work_description(work_key):
    if not work_key or not work_key.startswith("/works/"):
        return ""

    try:
        response = requests.get(
            OPEN_LIBRARY_WORK_URL.format(key=work_key),
            headers=_headers(),
            timeout=4,
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    description = response.json().get("description", "")
    if isinstance(description, dict):
        return description.get("value", "")
    if isinstance(description, str):
        return description
    return ""


def _search_open_library(query, limit):
    params = {
        "q": query,
        "limit": limit,
        "fields": "key,title,author_name,cover_i,first_publish_year,isbn,subject",
    }

    try:
        response = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params=params,
            headers=_headers(),
            timeout=4,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OpenLibraryError("Open Library search failed.") from exc

    docs = response.json().get("docs", [])
    return [_normalize_open_library(doc) for doc in docs if doc.get("title")]


def _search_google_books(query, limit):
    params = {
        "q": query,
        "maxResults": limit,
        "printType": "books",
    }

    try:
        response = requests.get(GOOGLE_BOOKS_SEARCH_URL, params=params, timeout=4)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BookApiError("Google Books search failed.") from exc

    items = response.json().get("items", [])
    return [_normalize_google_book(item) for item in items if item.get("volumeInfo", {}).get("title")]


def _normalize_open_library(doc):
    authors = doc.get("author_name") or []
    isbn_values = doc.get("isbn") or []
    subjects = doc.get("subject") or []
    cover_id = doc.get("cover_i")

    return {
        "provider": "Open Library",
        "key": doc.get("key", ""),
        "title": doc.get("title", "Untitled"),
        "authors": ", ".join(authors[:3]) if authors else "Unknown author",
        "published_year": doc.get("first_publish_year"),
        "isbn": isbn_values[0] if isbn_values else "",
        "subjects": subjects[:4],
        "description": "",
        "cover_image": OPEN_LIBRARY_COVER_URL.format(cover_id=cover_id) if cover_id else "",
    }


def _normalize_google_book(item):
    info = item.get("volumeInfo", {})
    authors = info.get("authors") or []
    identifiers = info.get("industryIdentifiers") or []
    isbn = next(
        (identifier.get("identifier") for identifier in identifiers if "ISBN" in identifier.get("type", "")),
        "",
    )
    image_links = info.get("imageLinks") or {}
    published_date = info.get("publishedDate", "")

    return {
        "provider": "Google Books",
        "key": item.get("id", ""),
        "title": info.get("title", "Untitled"),
        "authors": ", ".join(authors[:3]) if authors else "Unknown author",
        "published_year": _year_from_date(published_date),
        "isbn": isbn,
        "subjects": (info.get("categories") or [])[:4],
        "description": info.get("description", ""),
        "cover_image": image_links.get("thumbnail", "").replace("http://", "https://"),
    }


def _headers():
    user_agent = "BookNestStudentProject/1.0"
    try:
        user_agent = current_app.config.get("OPEN_LIBRARY_USER_AGENT", user_agent)
    except RuntimeError:
        pass
    return {"User-Agent": user_agent}


def _cache_key(kind, query, limit):
    normalized = " ".join(query.lower().split())
    return f"{kind}:{normalized}:{limit}"


def _read_cache(cache_key, fresh_only):
    db = get_db()
    cur = db.cursor()
    if fresh_only:
        cur.execute(
            """
            SELECT provider, response_json, cached_at
            FROM api_cache
            WHERE cache_key = ?
              AND cached_at >= DATETIME('now', ?)
            """,
            (cache_key, f"-{CACHE_TTL_HOURS} hours"),
        )
    else:
        cur.execute(
            "SELECT provider, response_json, cached_at FROM api_cache WHERE cache_key = ?",
            (cache_key,),
        )
    row = cur.fetchone()
    db.close()

    if not row:
        return None

    return {
        "provider": row["provider"],
        "results": json.loads(row["response_json"]),
        "cached_at": row["cached_at"],
    }


def _write_cache(cache_key, provider, results):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO api_cache (cache_key, provider, response_json, cached_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(cache_key) DO UPDATE SET
            provider = excluded.provider,
            response_json = excluded.response_json,
            cached_at = CURRENT_TIMESTAMP
        """,
        (cache_key, provider, json.dumps(results)),
    )
    db.commit()
    db.close()


def _status(results, provider, cached, source="live", stale=False, error="", details=None):
    return {
        "results": results,
        "provider": provider,
        "cached": cached,
        "stale": stale,
        "source": source,
        "error": error,
        "details": details or [],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _year_from_date(value):
    if not value:
        return None
    try:
        return int(value[:4])
    except (TypeError, ValueError):
        return None


def _normalize_text(value):
    return " ".join((value or "").lower().replace(".", "").split())
