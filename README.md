# TechStore / MPOS_Flask

A modular Point of Sale (POS) and E-Commerce web application built with **Python Flask**, **SQLAlchemy**, **Jinja2**, and **Tailwind CSS**. 

The system provides a customer-facing storefront, an administrative back-office with role-based access and security auditing, integrated Telegram bot notifications for sales and rate-limit violations, and a RESTful API backend configured with CORS for external single-page applications (e.g., Angular).

---

## Table of Contents
1. [Key Features](#key-features)
2. [Tech Stack & Dependencies](#tech-stack--dependencies)
3. [Project Architecture & Directory Structure](#project-architecture--directory-structure)
4. [Module Overview](#module-overview)
   - [Storefront (`front_bp`)](#1-storefront--customer-portal-front_bp)
   - [Admin Portal (`admin_bp`)](#2-admin-portal-admin_bp)
   - [RESTful API (`api_bp`)](#3-restful-api-api_bp)
   - [Security & Rate Limiting](#4-security-rate-limiting--audit-logging)
   - [Helpers & Media Uploads](#5-helpers--media-pipeline)
5. [Database Models & Schema](#database-models--schema)
6. [Telegram Bot Integration](#telegram-bot-integration)
7. [Environment Configuration (`.env`)](#environment-configuration-env)
8. [Installation & Team Onboarding Setup](#installation--team-onboarding-setup)
9. [API Reference](#api-reference)
10. [Database Migrations Guide](#database-migrations-guide)
11. [Collaboration Guidelines](#collaboration-guidelines)

---

## Key Features

### 🛍️ Customer Storefront (`/`)
- **Product Catalog & Details**: Browse products by category, inspect specifications, and view related items.
- **Cookie-Based Shopping Cart**: Persistent, client-side cart management stored in HTTP cookies with server-side validation.
- **Cart Context Processor**: Dynamic cart item count automatically injected into navigation bars.
- **Checkout & Order Dispatch**: Automated order number generation, total calculations, and instant order broadcast to a Telegram channel.

### 🛡️ Admin Dashboard (`/admin`)
- **Authentication & Authorization**: Session-based authentication with Werkzeug password hashing.
- **User Management (CRUD)**: Manage administrative and staff accounts with profile pictures and roles (`admin`, `user`).
- **Profile Image Processing**: Automatic image resizing, RGBA conversion, and dual generation of original and 200x200 thumbnail images via Pillow.
- **Security & Block Log Center**: View, search, and delete 429 rate-limit violation logs with metric summaries (total blocks, unique IPs, targeted endpoints).

### 🚀 Developer & Integration Capabilities
- **RESTful API (`/api`)**: Clean JSON endpoints for products and users.
- **CORS Support**: Pre-configured Flask-CORS for cross-origin SPA frontends (e.g., `http://localhost:4200`).
- **CSRF Protection**: Comprehensive CSRF defense via Flask-WTF, intelligently bypassed for `/api/*` endpoints.
- **Rate-Limiter with Threat Notification**: Real-time traffic throttling via Flask-Limiter; triggers background Telegram security alerts on limit breach.

---

## Tech Stack & Dependencies

| Layer | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | Flask 3.1.3 | Lightweight WSGI web application framework |
| **ORM / Database** | Flask-SQLAlchemy 3.1.1 & SQLAlchemy 2.0.51 | Object Relational Mapper (SQLite / MySQL) |
| **Migrations** | Flask-Migrate 4.1.0 & Alembic 1.18.5 | Database schema versioning and migration tool |
| **Security & Forms** | Flask-WTF 1.3.0 & WTForms 3.2.2 | Form handling and CSRF defense |
| **Rate Limiting** | Flask-Limiter 4.1.1 | Request rate limiting by client IP |
| **CORS** | flask-cors 6.0.5 | Cross-Origin Resource Sharing handling |
| **Image Processing** | Pillow (PIL) 12.3.0 | Image resizing and thumbnail generation |
| **HTTP Client** | requests 2.34.2 | Dispatches Telegram webhook notifications |
| **Config / Env** | python-dotenv 1.2.3 | Loads environment variables from `.env` |
| **Frontend** | Jinja2, Tailwind CSS (CDN), Bootstrap Icons | Responsive UI rendering and styling |

---

## Project Architecture & Directory Structure

```text
Flask/
├── admin/                     # Admin Portal Blueprint
│   ├── __init__.py            # Blueprint definition & admin session guard hook
│   ├── auth.py                # Admin Login, Registration, and Logout
│   ├── block_log.py           # Block Log viewer, metrics & audit actions
│   ├── dashboard.py           # Admin control panel
│   └── user.py                # User CRUD & profile image management
├── api/                       # RESTful API Blueprint (JSON endpoints)
│   ├── __init__.py            # API Blueprint registration
│   ├── product.py             # Product listing, search, category & detail APIs
│   └── user.py                # User listing and detail APIs
├── front/                     # Customer Storefront Blueprint
│   ├── __init__.py            # Front Blueprint registration
│   ├── cart.py                # Cookie-based cart logic & context processors
│   ├── checkout.py            # Checkout processing & Telegram order dispatch
│   ├── home.py                # Storefront landing page
│   └── product.py             # Product catalog & single product views
├── helpers/                   # Reusable Utilities
│   ├── __init__.py            # Helper exports
│   ├── telegram.py            # Async Telegram rate-limit alert dispatcher with cooldown
│   └── upload.py              # File validation, thumbnail generator & deletion
├── instance/                  # Local instance files
│   └── mydb.sqlite3           # Default SQLite database
├── migrations/                # Alembic database migration scripts
│   ├── versions/              # Migration history
│   └── env.py                 # Alembic environment configuration
├── models/                    # SQLAlchemy Database Models
│   ├── __init__.py            # Models export
│   ├── block_log.py           # BlockLog model (for 429 rate limit auditing)
│   └── user.py                # User model (accounts, credentials, roles)
├── static/                    # Static Assets
│   ├── admin/                 # Admin styles and JavaScript
│   ├── assets/                # Banners and payment QR codes
│   ├── images/                # Uploaded media (user avatars, thumbnails)
│   └── style/                 # Customer storefront styles
├── templates/                 # Jinja2 Templates
│   ├── admin/                 # Admin layout, shared components & views
│   ├── Error/                 # Custom error pages (400, 404, 429, 500)
│   ├── front/                 # Storefront views (home, catalog, cart, checkout)
│   ├── login.html             # Login view
│   └── register.html          # Registration view
├── app.py                     # Application entry point & extension setup
├── config.py                  # Configuration loader & default settings
├── errors.py                  # Global error handlers (400, 404, 429, 500)
├── extensions.py              # Shared Flask extensions (db, limiter, csrf, cors)
├── product.py                 # In-memory product catalog & query functions
├── requirements.txt           # Python dependency specifications
├── .env.example               # Environment variables template
└── README.md                  # Project documentation
```

---

## Module Overview

### 1. Storefront / Customer Portal (`front_bp`)
- **URL Prefix**: `/`
- **Templates**: `templates/front/`
- **Key Routes**:
  - `GET /`: Home landing page with featured products.
  - `GET /products`: Full product catalog.
  - `GET /product/<id>`: Product specifications and related category items.
  - `GET /cart?product_id=<id>&qty=<n>`: View cart or add a product to cart.
  - `GET /update_cart?product_id=<id>&qty=<n>`: Update item quantity or remove item if quantity `< 1`.
  - `GET /remove_from_cart?product_id=<id>`: Remove item from cart.
  - `GET /checkout`: Review order items, subtotal, and payment instructions.
  - `POST /checkout`: Submit billing details, trigger order dispatch to Telegram, and clear cart cookie.

### 2. Admin Portal (`admin_bp`)
- **URL Prefix**: `/admin`
- **Templates**: `templates/admin/`
- **Authentication Guard**: Enforced via `@admin_bp.before_request`; redirects unauthenticated sessions to `/admin/login`.
- **Key Routes**:
  - `GET /admin/login`, `POST /admin/login`: Authenticate admin/staff (throttled to 5 attempts/min).
  - `GET /admin/register`, `POST /admin/register`: Account creation with duplicate checks.
  - `GET /admin/logout`: Clear session.
  - `GET /admin/dashboard`: Overview screen.
  - `GET /admin/user`: List users with thumbnails, roles, and emails.
  - `GET /admin/user/add`, `POST /admin/user/add`: Create user and upload profile picture.
  - `GET /admin/user/edit/<id>`, `POST /admin/user/edit`: Update profile, change password, or replace avatar.
  - `GET /admin/user/confirm-delete/<id>`, `POST /admin/user/delete`: Delete user and prune associated avatar files.
  - `GET /admin/block-logs`: Audit table of 429 security events with IP, endpoint, method, user-agent, and search filtering.
  - `POST /admin/block-logs/clear`: Truncate all block logs.
  - `POST /admin/block-logs/delete/<id>`: Delete a single block log record.

### 3. RESTful API (`api_bp`)
- **URL Prefix**: `/api`
- **CORS Configuration**: Enabled for `http://localhost:4200` to support Angular or other SPA frontends.
- **CSRF**: Explicitly exempted using `csrf.exempt(api_bp)`.
- **Response Format**: JSON.

### 4. Security, Rate Limiting & Audit Logging
The application uses **Flask-Limiter** with custom error interception in `errors.py`:
1. **Global Default Limits**: `10000 per day`, `100 per minute` per client IP.
2. **Endpoint Limits**: Stricter rules on sensitive routes (e.g. login: `5 per minute`).
3. **Automated Incident Logging**:
   - On a `429 Too Many Requests` trigger, `errors.py` intercepts the request.
   - Saves violation details (`ip`, `endpoint`, `methods`, `attempts`, `device`, `create_at`) into the `block_logs` table.
4. **Instant Telegram Alerts**:
   - `helpers/telegram.py` launches an asynchronous background thread.
   - Formats a security alert card and posts to the Telegram Alert Channel.
   - Features a 60-second in-memory IP cooldown to prevent bot-flooding the Telegram API.

### 5. Helpers & Media Pipeline
- **`helpers/upload.py`**:
  - Verifies file extensions against `ALLOWED_EXTENSIONS` (`png`, `jpg`, `jpeg`, `gif`).
  - Sanitizes filenames using `werkzeug.utils.secure_filename`.
  - Generates two files: `{id}_org_{username}.ext` and `{id}_thumb_{username}.ext` (resized to 200x200 via Lanczos filter).
  - Handles automatic file cleanup on disk when users update or delete avatars.

---

## Database Models & Schema

### `User` Table (`user`)
Stores user accounts for authentication and administration.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Auto-increment | Unique user ID |
| `username` | `String(80)` | Not Null | Account username |
| `email` | `String(120)` | Unique, Not Null | Account email address |
| `password` | `String(255)` | Not Null | Hashed password (`generate_password_hash`) |
| `role` | `String(120)` | Not Null, Default: `'user'` | Access role (`admin`, `user`) |
| `profile` | `String(80)` | Nullable | Stored filename of the original profile image |

### `BlockLog` Table (`block_logs`)
Captures rate-limit breaches and potential brute-force or DoS attempts.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Auto-increment | Log identifier |
| `ip` | `String(100)` | Not Null | Client IP address (extracts `X-Forwarded-For` if behind proxy) |
| `endpoint` | `String(255)` | Not Null | Targeted path / route |
| `methods` | `String(20)` | Not Null | HTTP method (`GET`, `POST`, etc.) |
| `attempts` | `String(100)` | Nullable | Rate limit rule / description triggered |
| `device` | `String(500)` | Nullable | Request `User-Agent` |
| `create_at` | `DateTime` | Not Null, Default: UTC | Timestamp of the event |

---

## Telegram Bot Integration

The project includes two independent Telegram notification channels configured via environment variables:

1. **Customer Order Channel**:
   - Triggered on successful checkout (`front/checkout.py`).
   - Delivers a formatted HTML receipt showing customer name, delivery address, phone, payment method, ordered items with quantities, and total amount.
2. **Security Alert Channel**:
   - Triggered on 429 rate limit events (`helpers/telegram.py`).
   - Alerts administrators with the offending IP, method, endpoint, remaining cooldown time, device user-agent, and local timestamp (GMT+7).

---

## Environment Configuration (`.env`)

Create a `.env` file in the project root directory (you can copy `.env.example`):

```bash
cp .env.example .env
```

### Supported Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `SECRET_KEY` | Yes | `secret` | Cryptographic secret for signing sessions & CSRF tokens |
| `FLASK_APP` | No | `app.py` | Flask entry file |
| `FLASK_DEBUG` | No | `1` | Enable/disable Flask debug mode |
| `SQLALCHEMY_DATABASE_URI` | No | `sqlite:///mydb.sqlite3` | Database connection URI |
| `STORE_NAME` | No | `TechStore` | Storefront branding name |
| `STORE_TIMEZONE` | No | `Asia/Phnom_Penh` | Reporting & display timezone (GMT+7) |
| `LOW_STOCK_THRESHOLD` | No | `5` | Fallback inventory alert threshold |
| `GRACE_PERIOD_HOURS` | No | `4` | Auto-confirmation window for pending orders |
| `SCHEDULER_ENABLED` | No | `True` | Enable APScheduler background jobs |
| `TELEGRAM_BOT_TOKEN` | Optional | `""` | Bot token for sending customer order receipts |
| `TELEGRAM_CHAT_ID` | Optional | `@SETEC_PP_SHOP` | Chat / Channel ID for order alerts |
| `TELEGRAM_ALERT_BOT_TOKEN` | Optional | `""` | Bot token for security & rate-limit alerts |
| `TELEGRAM_ALERT_CHAT_ID` | Optional | `@pp_shop_alert` | Chat / Channel ID for security alerts |

> **Database Note**: The default database URI is SQLite (`sqlite:///mydb.sqlite3`). To switch to MySQL, update `config.py` or `.env` with `mysql+pymysql://<user>:<password>@<host>/<database>` and install `pymysql`.

---

## Installation & Team Onboarding Setup

Follow these steps to set up and run the project locally on your machine.

### 1. Clone the Repository & Check Out Work Branch
```bash
git clone <repository-url>
cd Flask
```

### 2. Create and Activate a Virtual Environment
- **On Windows (PowerShell / Command Prompt)**:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\activate
  ```
- **On macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```

### 5. Apply Database Migrations
Run Alembic migrations to create all database tables:
```bash
flask db upgrade
```

### 6. Seed Product Catalog & Development Coupons
Run the idempotent seed script to populate categories, products, default variants, and sample coupons:
```bash
python scripts/seed_catalog.py
```

### 7. Run Test Suite
Verify that all system smoke tests pass:
```bash
pytest
```

### 8. Start the Development Server
```bash
python app.py
```
Or alternatively:
```bash
flask run --debug
```

The application will start on `http://127.0.0.1:5000/`.

The application will start on `http://127.0.0.1:5000/`.

---

## API Reference

All API routes are served under the `/api` prefix and return JSON.

### Product Endpoints

#### 1. Get All Products
`GET /api/products` (alias: `GET /api/product`)
- **Query Parameters**:
  - `category` *(optional)*: Filter products by category (case-insensitive).
  - `q` *(optional)*: Search keyword matching product name or description.
- **Example Response**:
  ```json
  {
    "success": true,
    "count": 1,
    "data": [
      {
        "id": 1,
        "name": "MSI Katana 15",
        "category": "Laptop",
        "price": 1299.99,
        "stock": 12,
        "description": "Gaming laptop with Intel Core i7...",
        "image": "https://..."
      }
    ]
  }
  ```

#### 2. Get Product by ID
`GET /api/products/<product_id>` (alias: `GET /api/product/<product_id>`)
- **Example Response (`200 OK`)**:
  ```json
  {
    "success": true,
    "data": {
      "id": 1,
      "name": "MSI Katana 15",
      "price": 1299.99
    }
  }
  ```
- **Error Response (`404 Not Found`)**:
  ```json
  {
    "success": false,
    "error": "Product not found"
  }
  ```

#### 3. Get All Product Categories
`GET /api/products/categories`
- **Example Response**:
  ```json
  {
    "success": true,
    "categories": [
      "Cooling",
      "Graphics Card",
      "Headset",
      "Laptop",
      "Monitor",
      "Motherboard",
      "Mouse",
      "PC Case"
    ]
  }
  ```

---

### User Endpoints

#### 1. Get All Users
`GET /api/users` (alias: `GET /api/user`)
- **Example Response**:
  ```json
  [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "profile": "1_org_admin.jpg"
    }
  ]
  ```

#### 2. Get User by ID
`GET /api/user/<user_id>`
- **Example Response (`200 OK`)**:
  ```json
  {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin",
    "profile": "1_org_admin.jpg"
  }
  ```
- **Error Response (`404 Not Found`)**:
  ```json
  {
    "error": "User not found"
  }
  ```

---

## Database Migrations Guide

When modifying or adding models in `models/`:

1. **Generate a migration script**:
   ```bash
   flask db migrate -m "Describe your schema changes"
   ```
2. **Review the generated file** in `migrations/versions/`.
3. **Apply the migration to your database**:
   ```bash
   flask db upgrade
   ```
4. **Revert a migration** (if needed):
   ```bash
   flask db downgrade
   ```

---

## Collaboration Guidelines

When collaborating on this project:

1. **Branch Naming**:
   - `feature/feature-name` (e.g., `feature/order-history`)
   - `fix/bug-name` (e.g., `fix/cart-cookie-parser`)
   - `docs/doc-update`
2. **Security & Secrets**:
   - Never commit sensitive keys, `.env` files, or production credentials to Git.
   - Always verify that `.env` remains in `.gitignore`.
3. **Forms & CSRF**:
   - When building new HTML forms in templates, include the CSRF token:
     ```html
     <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
     ```
4. **URL Generation**:
   - Use `url_for('<blueprint_name>.<view_function>')` (e.g. `url_for('front_bp.product', product_id=p.id)`).
5. **Static Media Handling**:
   - When uploading images, utilize the helpers in `helpers/upload.py` to ensure proper thumb generation and automatic cleanup of previous images.
