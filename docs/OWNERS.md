# Workstream Ownership & File Map

To allow 4 teammates to develop features concurrently without merge conflicts, all files are divided into strict ownership boundaries:

---

## 🔒 Protected Core (Team Lead Only)
No teammate or AI agent may edit these files without explicit approval:
- `models/*`
- `migrations/*`
- `app.py`
- `config.py`
- `extensions.py`
- `requirements.txt`
- `tests/conftest.py`
- `docs/ARCHITECTURE.md`
- `AGENTS.md`

---

## 👨‍💻 Workstream A: Catalog, Product Variants & Low-Stock Alerts
- `admin/products.py`
- `services/stock_service.py`
- `templates/admin/products/*`
- Tests: `tests/test_catalog_variants.py`

---

## 👩‍💻 Workstream B: Customer Accounts, Wishlist & Reviews
- `front/auth.py`
- `front/account.py`
- `front/wishlist.py`
- `front/reviews.py`
- `templates/front/account/*`
- `templates/front/wishlist/*`
- Tests: `tests/test_customer_wishlist.py`

---

## 👨‍💻 Workstream C: Orders, Checkout Transitions & Grace Period Confirmer
- `front/checkout.py`
- `admin/orders.py`
- `services/order_service.py`
- `jobs/grace_period.py`
- `templates/admin/orders/*`
- Tests: `tests/test_orders_grace_period.py`

---

## 👩‍💻 Workstream D: Coupons, Invoicing (PDF) & Accounting Exports (CSV/Excel)
- `front/invoice.py`
- `admin/coupons.py`
- `admin/reports.py`
- `services/coupon_service.py`
- `services/report_service.py`
- `templates/admin/coupons/*`
- `templates/admin/reports/*`
- Tests: `tests/test_coupons_reports.py`
