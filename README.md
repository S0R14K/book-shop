# BookShop - Online Bookstore Application

A full-featured online bookstore web application built with Flask, featuring user authentication, shopping cart, wishlist, order management, and admin dashboard.

## Features

 **User Features**
- User registration and login with secure password hashing
- Browse and search for books with filters (price, category)
- Add books to shopping cart
- Wishlist functionality
- Checkout and order placement
- Order history and tracking
- User profile management
- Currency conversion (EUR to other currencies)

 **Admin Features**
- Admin dashboard with statistics
- Add, edit, and delete books
- Manage book categories
- View and update order status
- Book inventory management

 **Technical Features**
- External book search integration (Open Library, Google Books)
- Caching system for API responses
- CSRF protection
- Responsive design with Bootstrap
- SQLite database
- RESTful API endpoints

## Tech Stack

- **Backend:** Flask 3.0+
- **Frontend:** HTML5, CSS3, JavaScript
- **Database:** SQLite3
- **Authentication:** Flask-WTF, Werkzeug
- **External APIs:** Open Library API, Google Books API, Exchange Rate API

## Installation

### Prerequisites
- Python 3.8+
- pip (Python package manager)
- Git

### Clone the Repository
```bash
git clone https://github.com/yourusername/book-shop.git
cd book-shop
```

### Create Virtual Environment
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
source .venv/bin/activate  # On macOS/Linux
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Initialize Database
```bash
cd book-shop-main
python bookshop/init_database.py
```

## Running the Application

Start the Flask development server:
```bash
cd book-shop-main
python run_server.py
```

The application will be available at `http://127.0.0.1:5000`

### Default Admin Access
After initialization, you can create an admin account by registering and updating the `is_admin` flag in the database.

## Project Structure

```
book-shop-main/
├── bookshop/
│   ├── __init__.py
│   ├── app.py                 # Flask app factory
│   ├── config.py              # Configuration settings
│   ├── db.py                  # Database connection
│   ├── utils.py               # Utility functions
│   ├── sample_data.py         # Default book data
│   ├── init_database.py       # Database initialization
│   ├── seed_books.py          # Seed database script
│   ├── models/
│   │   └── user.py            # User model
│   ├── routes/
│   │   ├── auth.py            # Authentication routes
│   │   ├── shop.py            # Shop/catalog routes
│   │   ├── cart_routes.py     # Shopping cart routes
│   │   ├── order.py           # Order/checkout routes
│   │   ├── account.py         # User account routes
│   │   ├── admin.py           # Admin dashboard routes
│   │   └── api_routes.py      # API endpoints
│   ├── services/
│   │   └── open_library.py    # External API integration
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css
│   │   └── js/
│   │       └── main.js
│   ├── templates/
│   │   ├── base.html          # Base template
│   │   ├── index.html
│   │   ├── books.html
│   │   ├── book_detail.html
│   │   ├── cart.html
│   │   ├── checkout.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── profile.html
│   │   ├── wishlist.html
│   │   ├── orders.html
│   │   ├── order_details.html
│   │   ├── confirmation.html
│   │   ├── admin/
│   │   │   ├── dashboard.html
│   │   │   ├── books.html
│   │   │   ├── categories.html
│   │   │   ├── orders.html
│   │   │   └── book_form.html
│   │   ├── errors/
│   │   │   ├── 404.html
│   │   │   └── 500.html
│   │   └── partials/
│   │       └── book_card.html
│   └── instance/               # Database location
│
├── run_server.py              # Entry point
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

## Database Schema

### Users Table
- `id` - Primary key
- `email` - Unique email address
- `password_hash` - Hashed password
- `is_admin` - Admin flag
- `created_at` - Timestamp

### Books Table
- `id` - Primary key
- `title` - Book title
- `author` - Author name
- `description` - Book description
- `price_eur` - Price in EUR
- `stock` - Available quantity
- `cover_image` - Cover image URL
- `category` - Category name
- `category_id` - Foreign key to categories
- `slug` - URL-friendly identifier
- `isbn` - ISBN number
- `published_year` - Publication year
- `featured` - Featured flag
- `is_active` - Active flag

### Orders & Cart
- `cart_items` - Shopping cart items per user
- `orders` - Order history
- `order_items` - Items in each order
- `wishlist_items` - User wishlist items

### Other Tables
- `categories` - Book categories
- `api_cache` - External API response cache

## API Endpoints

### Public Routes
- `GET /` - Home page
- `GET /books` - Browse books with filtering
- `GET /books/<slug>` - Book details
- `GET /about` - About page

### Authentication
- `POST /register` - User registration
- `POST /login` - User login
- `GET /logout` - User logout

### Shopping
- `GET /cart` - View cart
- `POST /cart/add/<book_id>` - Add to cart
- `POST /cart/update/<item_id>` - Update cart item
- `POST /cart/remove/<item_id>` - Remove from cart

### Orders
- `GET /checkout` - Checkout page
- `POST /checkout` - Place order
- `GET /order/<order_id>` - Order confirmation
- `GET /orders` - Order history
- `GET /order/details/<order_id>` - Order details

### Account
- `GET /profile` - User profile
- `GET /wishlist` - User wishlist
- `POST /wishlist/add/<book_id>` - Add to wishlist
- `POST /wishlist/remove/<book_id>` - Remove from wishlist

### Admin Routes
- `GET /admin/` - Dashboard
- `GET /admin/books` - Book management
- `GET /admin/books/new` - Add new book
- `POST /admin/books/<book_id>/edit` - Edit book
- `POST /admin/books/<book_id>/delete` - Delete book
- `GET /admin/categories` - Category management
- `GET /admin/orders` - Order management

### API Endpoints
- `GET /api/convert` - Currency conversion
- `GET /api/open-library/search` - External book search
- `GET /api/book-enrichment` - Book metadata enrichment

## Configuration

Edit `bookshop/config.py` to customize:
```python
SECRET_KEY = "your-secret-key"           # Change for production
DATABASE = "instance/bookshop.sqlite"    # Database location
FLASK_ENV = "development"                # Or "production"
```

## Environment Variables

Set these for production:
```bash
FLASK_SECRET_KEY=your-production-secret-key
OPEN_LIBRARY_USER_AGENT=YourApp/1.0 (your@email.com)
```

## Security Notes

 **Important for Production:**
- Change `SECRET_KEY` in `config.py`
- Use HTTPS in production
- Set `debug=False` in `run_server.py`
- Use a production WSGI server (Gunicorn, uWSGI)
- Implement proper password policies
- Add rate limiting for APIs
- Set secure session cookies

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, email your-email@example.com or open an issue on GitHub.

## Authors

- Created as a coursework project

## Acknowledgments

- Flask documentation and community
- Open Library API for book data
- Google Books API integration
- Bootstrap for responsive design
