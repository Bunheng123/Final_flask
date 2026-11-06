import os
import sys

# Ensure parent directory is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app
from extensions import db
from models.category import Category
from models.product import Product
from models.product_variant import ProductVariant
from models.coupon import Coupon
from product import products
from helpers.money import to_cents

def slugify(text: str) -> str:
    return text.lower().strip().replace(' ', '-').replace('/', '-')

def seed_catalog():
    print("Starting catalog & sample coupon seeding...")

    # 1. Seed Categories
    category_map = {}
    categories_created = 0
    unique_cats = sorted(list({p.get('category') for p in products if p.get('category')}))
    for cat_name in unique_cats:
        slug = slugify(cat_name)
        cat = Category.query.filter_by(name=cat_name).first()
        if not cat:
            cat = Category(name=cat_name, slug=slug)
            db.session.add(cat)
            db.session.flush()
            categories_created += 1
        category_map[cat_name] = cat.id

    # 2. Seed Products and Variants
    products_created = 0
    variants_created = 0
    for p in products:
        cat_id = category_map[p['category']]
        prod = Product.query.filter_by(name=p['name']).first()
        if not prod:
            prod = Product(
                name=p['name'],
                category_id=cat_id,
                description=p.get('description', ''),
                image=p.get('image', ''),
                is_active=True
            )
            db.session.add(prod)
            db.session.flush()
            products_created += 1

        # Deterministic SKU based on product id
        sku = f"SKU-{p['id']:04d}-DEF"
        variant = ProductVariant.query.filter_by(sku=sku).first()
        if not variant:
            price_cents = to_cents(p.get('price', 0))
            cost_cents = int(price_cents * 0.70)  # estimated 70% cost basis
            variant = ProductVariant(
                product_id=prod.id,
                sku=sku,
                spec_name="Default",
                price_cents=price_cents,
                cost_price_cents=cost_cents,
                stock=int(p.get('stock', 0)),
                low_stock_threshold=5,
                is_active=True
            )
            db.session.add(variant)
            variants_created += 1

    # 3. Seed Sample Coupons (for dev/testing)
    coupons_created = 0
    sample_coupons = [
        {
            "code": "WELCOME10",
            "discount_type": "percent",
            "value": 10.0,
            "min_spend_cents": 5000,      # $50.00
            "max_discount_cents": 2000,   # $20.00 max discount
            "usage_limit": 100,
            "per_customer_limit": 1,
            "is_active": True
        },
        {
            "code": "SAVE20",
            "discount_type": "fixed",
            "value": 2000.0,              # $20.00 fixed discount
            "min_spend_cents": 10000,     # $100.00
            "max_discount_cents": 2000,
            "usage_limit": 50,
            "per_customer_limit": 1,
            "is_active": True
        }
    ]

    for c_data in sample_coupons:
        c = Coupon.query.filter_by(code=c_data["code"]).first()
        if not c:
            c = Coupon(**c_data)
            db.session.add(c)
            coupons_created += 1

    db.session.commit()
    print(f"Seeding completed successfully:")
    print(f" - Categories created: {categories_created} (Total: {Category.query.count()})")
    print(f" - Products created:   {products_created} (Total: {Product.query.count()})")
    print(f" - Variants created:   {variants_created} (Total: {ProductVariant.query.count()})")
    print(f" - Coupons created:    {coupons_created} (Total: {Coupon.query.count()})")

if __name__ == '__main__':
    with app.app_context():
        seed_catalog()
