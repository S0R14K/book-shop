from bookshop.app import init_db


def seed_books():
    init_db()
    print("Default bookstore inventory is ready.")


if __name__ == "__main__":
    seed_books()
