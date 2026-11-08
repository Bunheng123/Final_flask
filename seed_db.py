"""
Database Seeding & Test Data Initialization Script
Allows teammates to initialize all database tables and populate the database
with categories, brands, products, variants, and test users, with all variant
prices set to $0.01 (1 cent) for seamless checkout & payment testing.

Usage:
    python seed_db.py
"""
import os
import sys
import random
from typing import Optional

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app
from extensions import db
from models.user import User
from models.category import Category
from models.brand import Brand
from models.product import Product
from models.product_variant import ProductVariant
from models.coupon import Coupon
from helpers.time import utc_now
from helpers.money import format_money
from werkzeug.security import generate_password_hash


def slugify(text: str) -> str:
    import re
    if not text:
        return ""
    text_val = re.sub(r'[^\w\s-]', '', str(text).strip().lower())
    return re.sub(r'[-\s]+', '-', text_val).strip('-')


def seed_database(test_price_cents: Optional[int] = None):
    print("=" * 60)
    print(" Initializing Database & Seeding Catalog with Random Test Prices ($0.01 - $0.03)")
    print("=" * 60)

    # 1. Create all database tables and apply pending migrations
    db.create_all()
    try:
        from flask_migrate import upgrade as migrate_upgrade
        migrate_upgrade()
    except Exception as e:
        print(f"  Note on migrations: {e}")

    # 2. Seed Default Users
    print("\n[1/5] Checking / Seeding Default Users...")
    admin_user = User.query.filter_by(username="admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            email="admin@shop.com",
            password=generate_password_hash("admin123"),
            role="admin",
            is_active=True,
            created_at=utc_now()
        )
        db.session.add(admin_user)
        print("  ✓ Created default admin: admin (password: admin123)")

    test_customer = User.query.filter_by(username="user").first()
    if not test_customer:
        test_customer = User(
            username="user",
            email="user@shop.com",
            password=generate_password_hash("user123"),
            role="user",
            is_active=True,
            created_at=utc_now()
        )
        db.session.add(test_customer)
        print("  ✓ Created default customer: user (password: user123)")

    db.session.flush()

    # 3. Seed Default Brands
    print("\n[2/5] Checking / Seeding Brands...")
    default_brands = [
        {"name": "Apple", "slug": "apple", "website": "https://apple.com"},
        {"name": "Lenovo", "slug": "lenovo", "website": "https://lenovo.com"},
        {"name": "Dell", "slug": "dell", "website": "https://dell.com"},
        {"name": "Samsung", "slug": "samsung", "website": "https://samsung.com"},
        {"name": "Sony", "slug": "sony", "website": "https://sony.com"},
        {"name": "MSI", "slug": "msi", "website": "https://msi.com"},
        {"name": "Logitech", "slug": "logitech", "website": "https://logitech.com"},
    ]
    brand_map = {}
    for b_data in default_brands:
        brand = Brand.query.filter((Brand.slug == b_data["slug"]) | (Brand.name.ilike(b_data["name"]))).first()
        if not brand:
            brand = Brand(
                name=b_data["name"],
                slug=b_data["slug"],
                website=b_data.get("website", ""),
                created_at=utc_now()
            )
            db.session.add(brand)
            db.session.flush()
            print(f"  ✓ Added brand: {brand.name}")
        brand_map[brand.name.lower()] = brand.id

    # 4. Seed Categories
    print("\n[3/5] Checking / Seeding Categories...")
    from product import products as raw_catalog
    category_map = {}
    unique_cats = sorted(list({p.get('category') for p in raw_catalog if p.get('category')}))
    for cat_name in unique_cats:
        slug = slugify(cat_name)
        cat = Category.query.filter((Category.slug == slug) | (Category.name.ilike(cat_name))).first()
        if not cat:
            cat = Category(name=cat_name, slug=slug)
            db.session.add(cat)
            db.session.flush()
            print(f"  ✓ Added category: {cat.name}")
        category_map[cat_name] = cat.id

    # 5. Seed Products and Variants
    print("\n[4/5] Checking / Seeding Products & Variants (Prices: $0.01 - $0.03)...")
    products_added = 0
    variants_added = 0
    variants_updated = 0

    for item in raw_catalog:
        cat_name = item.get('category', 'Laptops')
        cat_id = category_map.get(cat_name)

        # Detect brand from item name
        brand_id = None
        item_name_lower = item['name'].lower()
        for b_name, b_id in brand_map.items():
            if b_name in item_name_lower:
                brand_id = b_id
                break

        prod = Product.query.filter_by(name=item['name']).first()
        if not prod:
            prod = Product(
                name=item['name'],
                category_id=cat_id,
                brand_id=brand_id,
                description=item.get('description', ''),
                image=item.get('image', ''),
                is_active=True
            )
            db.session.add(prod)
            db.session.flush()
            products_added += 1

        # Define 3 rich variants per product
        cat_lower = cat_name.lower()
        if 'laptop' in cat_lower or 'desktop' in cat_lower or 'pc' in cat_lower:
            spec_configs = [
                ("Standard (16GB RAM / 512GB SSD)", f"SKU-{item['id']:04d}-DEF", 1, max(20, int(item.get('stock', 20)))),
                ("Pro (32GB RAM / 1TB SSD)", f"SKU-{item['id']:04d}-PRO", 2, 15),
                ("Max (64GB RAM / 2TB SSD)", f"SKU-{item['id']:04d}-MAX", 3, 10),
            ]
        elif 'graphic' in cat_lower or 'gpu' in cat_lower:
            spec_configs = [
                ("Standard (Core Clock)", f"SKU-{item['id']:04d}-DEF", 1, max(20, int(item.get('stock', 20)))),
                ("OC Edition (Factory Overclock)", f"SKU-{item['id']:04d}-PRO", 2, 15),
                ("Liquid Cooled Edition", f"SKU-{item['id']:04d}-MAX", 3, 10),
            ]
        elif 'monitor' in cat_lower or 'display' in cat_lower:
            spec_configs = [
                ("Standard (144Hz IPS)", f"SKU-{item['id']:04d}-DEF", 1, max(20, int(item.get('stock', 20)))),
                ("Pro (175Hz QHD HDR)", f"SKU-{item['id']:04d}-PRO", 2, 15),
                ("Max (240Hz OLED Curved)", f"SKU-{item['id']:04d}-MAX", 3, 10),
            ]
        elif 'storage' in cat_lower or 'ssd' in cat_lower:
            spec_configs = [
                ("512GB PCIe 4.0 NVMe", f"SKU-{item['id']:04d}-DEF", 1, max(25, int(item.get('stock', 20)))),
                ("1TB PCIe 4.0 NVMe", f"SKU-{item['id']:04d}-PRO", 2, 20),
                ("2TB PCIe 4.0 NVMe", f"SKU-{item['id']:04d}-MAX", 3, 15),
            ]
        else:
            spec_configs = [
                ("Standard Edition", f"SKU-{item['id']:04d}-DEF", 1, max(20, int(item.get('stock', 20)))),
                ("Pro Edition / Midnight", f"SKU-{item['id']:04d}-PRO", 2, 15),
                ("Titanium Max Ultra", f"SKU-{item['id']:04d}-MAX", 3, 10),
            ]

        for spec_name, sku, default_cents, stock_qty in spec_configs:
            variant = ProductVariant.query.filter_by(sku=sku).first()
            item_price_cents = test_price_cents if test_price_cents is not None else default_cents

            if not variant:
                variant = ProductVariant(
                    product_id=prod.id,
                    sku=sku,
                    spec_name=spec_name,
                    price_cents=item_price_cents,
                    cost_price_cents=1,
                    stock=stock_qty,
                    low_stock_threshold=5,
                    is_active=True
                )
                db.session.add(variant)
                variants_added += 1
            else:
                variant.spec_name = spec_name
                target_price = test_price_cents if test_price_cents is not None else default_cents
                if variant.price_cents != target_price or variant.stock <= 0:
                    variant.price_cents = target_price
                    if variant.stock <= 0:
                        variant.stock = stock_qty
                    variant.is_active = True
                    variants_updated += 1

    # Ensure all variants within each product have different distinct prices
    for prod in Product.query.all():
        for idx, v in enumerate(prod.variants):
            if v.sku and v.sku.endswith('-DEF'):
                target_v_price = test_price_cents if test_price_cents is not None else 1
            elif v.sku and v.sku.endswith('-PRO'):
                target_v_price = test_price_cents if test_price_cents is not None else 2
            elif v.sku and v.sku.endswith('-MAX'):
                target_v_price = test_price_cents if test_price_cents is not None else 3
            else:
                target_v_price = test_price_cents if test_price_cents is not None else (1 + (idx % 5))
            
            if v.price_cents != target_v_price:
                v.price_cents = target_v_price
                variants_updated += 1
            if v.stock <= 0:
                v.stock = 20
                v.is_active = True

    # 6. Seed Sample Testing Coupons
    print("\n[5/5] Checking / Seeding Test Coupons...")
    coupons = [
        {
            "code": "TEST1CENT",
            "discount_type": "percent",
            "value": 50.0,
            "min_spend_cents": 1,
            "max_discount_cents": 100,
            "usage_limit": 1000,
            "per_customer_limit": 10,
            "is_active": True
        },
        {
            "code": "WELCOME10",
            "discount_type": "percent",
            "value": 10.0,
            "min_spend_cents": 1,
            "max_discount_cents": 500,
            "usage_limit": 500,
            "per_customer_limit": 5,
            "is_active": True
        },
        {
            "code": "SAVE20",
            "discount_type": "percent",
            "value": 20.0,
            "min_spend_cents": 1,
            "max_discount_cents": 1000,
            "usage_limit": 500,
            "per_customer_limit": 5,
            "is_active": True
        }
    ]
    for c_data in coupons:
        c = Coupon.query.filter_by(code=c_data["code"]).first()
        if not c:
            c = Coupon(**c_data)
            db.session.add(c)
            print(f"  ✓ Added test coupon: {c.code}")
        else:
            c.min_spend_cents = c_data["min_spend_cents"]
            c.is_active = True
            c.discount_type = c_data["discount_type"]
            c.value = c_data["value"]
            print(f"  ✓ Updated test coupon: {c.code} (Min spend: 1¢)")

    # Also make sure any other existing test coupon has min_spend_cents = 1 for testing
    all_coupons = Coupon.query.all()
    for cp in all_coupons:
        if cp.min_spend_cents > 10:
            cp.min_spend_cents = 1
        cp.is_active = True

    db.session.commit()

    print("\n" + "=" * 60)
    print("✅ DATABASE SEEDING COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print(f"• Total Categories : {Category.query.count()}")
    print(f"• Total Brands     : {Brand.query.count()}")
    print(f"• Total Products   : {Product.query.count()}")
    print(f"• Total Variants   : {ProductVariant.query.count()} (Distinct tiered prices: $0.01 / $0.02 / $0.03)")
    print(f"• Total Users      : {User.query.count()} (admin / user)")
    print(f"• Total Coupons    : {Coupon.query.count()}")
    print("=" * 60)
    print("💡 Teammates can now launch the app with: python app.py")
    print("   All products on the storefront are now live, in-stock, with distinct tiered prices per variant.")
    print("=" * 60)


if __name__ == '__main__':
    with app.app_context():
        seed_database(test_price_cents=None)
