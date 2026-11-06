# Workstream Ownership & File Map (M1 - M5)

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
- `templates/admin/master.html`, `templates/admin/share/*`, `templates/front/share/*`

---

## 👨‍💻 M1: Catalog, Product Variants & Low-Stock Alerts (Workstream A)
- `admin/products.py` (`admin_bp.admin_products`, `admin_bp.product_variants`)
- `admin/variants.py` (`admin_bp.variant_add`, `admin_bp.variant_edit`, `admin_bp.variant_delete`)
- `services/stock_service.py`
- `templates/admin/products/*`
- Tests: `tests/test_catalog_variants.py`

---

## 👩‍💻 M2: User Accounts & Authentication (Workstream B - Auth)
- `front/auth.py` (`front_bp.login`, `front_bp.register`, `front_bp.logout`, `front_bp.forgot_password`, `front_bp.reset_password`)
- `front/account.py` (`front_bp.account`, `front_bp.account_orders`, `front_bp.account_order_detail`)
- `helpers/auth.py` (`login_required`, `admin_required`, `current_user`, `is_safe_next_url`)
- `services/auth_service.py`
- `templates/front/account/*`
- Tests: `tests/test_auth_account.py`

---

## 👨‍💻 M3: Orders, Checkout Transitions & Grace Period (Workstream C)
- `front/checkout.py` (`front_bp.checkout`, `front_bp.do_checkout`)
- `admin/orders.py` (`admin_bp.admin_orders`, `admin_bp.order_detail`, `admin_bp.order_update_status`)
- `services/order_service.py`
- `services/email_service.py` (`send_order_email`)
- `jobs/grace_period.py` (`auto_confirm_pending_orders_job`)
- `templates/admin/orders/*`
- Tests: `tests/test_orders_grace_period.py`

---

## 👩‍💻 M4: Coupons, Invoicing (PDF) & Accounting Exports (Workstream D)
- `front/coupon.py` (`front_bp.coupon_preview`)
- `front/invoice.py` (`front_bp.invoice_pdf`)
- `admin/coupons.py` (`admin_bp.admin_coupons`, `admin_bp.coupon_add`, `admin_bp.coupon_edit`, `admin_bp.coupon_delete`)
- `admin/reports.py` (`admin_bp.admin_reports`, `admin_bp.report_sales_csv`, `admin_bp.report_sales_excel`)
- `services/coupon_service.py`
- `services/report_service.py`
- `templates/front/partials/_coupon_box.html`
- `templates/admin/coupons/*`
- `templates/admin/reports/*`
- Tests: `tests/test_coupons_reports.py`

---

## 👩‍💻 M5: Wishlist & Reviews (Workstream B - Social)
- `front/wishlist.py` (`front_bp.wishlist`, `front_bp.wishlist_add`, `front_bp.wishlist_remove`)
- `front/reviews.py` (`front_bp.add_review`)
- `admin/reviews.py` (`admin_bp.admin_reviews`)
- `templates/front/partials/_wishlist_button.html`
- `templates/front/partials/_rating_stars.html`
- `templates/front/partials/_reviews.html`
- `templates/front/wishlist/*`
- Tests: `tests/test_user_wishlist.py`
