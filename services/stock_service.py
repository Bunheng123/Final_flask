"""
Stock Service - Inventory management and atomic stock adjustments.
Owner: Workstream A / Member 2 (Catalog, Product Variants & Low-Stock Alerts)
"""
import re
import sys
from typing import Optional, List, Union
from sqlalchemy import text
from flask import current_app

from extensions import db
from models.product import Product
from models.product_variant import ProductVariant
from models.brand import Brand
from models.category import Category
from helpers.money import to_cents, from_cents, format_money
from helpers.time import utc_now
from helpers import telegram
from helpers.telegram import send_telegram, send_low_stock_alert


_UNSET = object()


class StockServiceError(Exception):
    """Base exception for stock service operations."""
    pass


class InsufficientStockError(StockServiceError):
    """Raised when an inventory decrement cannot be fulfilled due to lack of stock."""
    pass


class VariantNotFoundError(StockServiceError):
    """Raised when a requested product variant does not exist."""
    pass


class ProductNotFoundError(StockServiceError):
    """Raised when a requested base product does not exist."""
    pass


def slugify(text_val: str) -> str:
    """Convert a string into a clean, URL-friendly slug."""
    if not text_val:
        return ""
    text_val = re.sub(r'[^\w\s-]', '', str(text_val).strip().lower())
    return re.sub(r'[-\s]+', '-', text_val).strip('-')


def _escape_html(text_val) -> str:
    if not text_val:
        return ""
    return str(text_val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _normalize_cents(amount: Union[float, int, str, None]) -> int:
    if amount is None:
        return 0
    if isinstance(amount, int):
        return amount
    return to_cents(amount)


def _get_fallback_low_stock_threshold() -> int:
    try:
        if current_app:
            return int(current_app.config.get('LOW_STOCK_THRESHOLD', 5))
    except Exception:
        pass
    try:
        from config import LOW_STOCK_THRESHOLD
        return int(LOW_STOCK_THRESHOLD)
    except Exception:
        return 5


def _notify_low_stock(variant: ProductVariant, threshold: int) -> None:
    """
    Dispatch a low-stock alert asynchronously via Telegram.
    Never raises an exception into the caller.
    """
    try:
        product_name = variant.product.name if variant.product else "Unknown Product"
        variant_desc = f"{product_name} - {variant.spec_name} (SKU: {variant.sku})"
        thresh_info = f" (Threshold: {threshold})" if threshold is not None else ""
        msg = (
            f"⚠️ <b>[LOW STOCK ALERT]</b>\n"
            f"Product/Variant: <b>{_escape_html(variant_desc)}</b>\n"
            f"Current Stock: <b>{variant.stock}</b>{thresh_info}\n"
            f"Please reorder inventory soon."
        )

        mod = sys.modules.get(__name__)
        local_send = getattr(mod, 'send_telegram', None)
        if local_send and local_send != telegram.send_telegram:
            local_send(msg)
        else:
            telegram.send_telegram(msg)
    except Exception as e:
        # Non-blocking background alert; never crash caller
        print(f"[StockService] Low stock alert dispatch failed: {e}")


def attach_view_attributes(product: Optional[Product]) -> Optional[Product]:
    """
    Attach calculated presentation attributes to a Product model instance
    for storefront templates (default variant, price, formatted price, stock count, brand/category names).
    """
    if not product:
        return None

    product.brand_name = product.brand.name if product.brand else None
    product.category_name = product.category.name if product.category else None

    active_vars = [v for v in product.variants if v.is_active]
    for v in product.variants:
        v.price = from_cents(v.price_cents)
        v.price_formatted = format_money(v.price_cents)
        v.in_stock = (v.stock > 0)

    if active_vars:
        default_var = next((v for v in active_vars if v.spec_name.lower() == 'default'), active_vars[0])
        product.default_variant = default_var
        product.price = from_cents(default_var.price_cents)
        product.price_formatted = format_money(default_var.price_cents)
        product.price_cents = default_var.price_cents
        product.stock = sum(v.stock for v in active_vars)
        product.in_stock = any(v.stock > 0 for v in active_vars)
    else:
        product.default_variant = None
        product.price = 0.0
        product.price_formatted = "$0.00"
        product.price_cents = 0
        product.stock = 0
        product.in_stock = False

    return product


# ==========================================
# 1. Product Queries & Management
# ==========================================

def get_active_products(
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    search: Optional[str] = None
) -> List[Product]:
    """
    Fetch active products and their linked product variants.
    Supports optional category filter, brand filter, and search query.
    """
    query = Product.query.filter(Product.is_active == True)
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if brand_id is not None:
        query = query.filter(Product.brand_id == brand_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (Product.name.ilike(term)) | (Product.description.ilike(term))
        )
    products = query.order_by(Product.id.asc()).all()
    for p in products:
        attach_view_attributes(p)
    return products


def get_all_products(
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None
) -> List[Product]:
    """
    Fetch all products (both active and inactive) for admin management.
    """
    query = Product.query
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if brand_id is not None:
        query = query.filter(Product.brand_id == brand_id)
    products = query.order_by(Product.id.asc()).all()
    for p in products:
        attach_view_attributes(p)
    return products


def get_product_by_id(product_id: int, only_active: bool = False) -> Optional[Product]:
    """
    Fetch a single product by primary key ID.
    """
    query = Product.query.filter(Product.id == product_id)
    if only_active:
        query = query.filter(Product.is_active == True)
    product = query.first()
    if product:
        attach_view_attributes(product)
    return product


def create_product(
    name: str,
    category_id: int,
    description: Optional[str] = None,
    image: Optional[str] = None,
    price_cents: Union[int, float, str] = 0,
    stock: int = 0,
    sku: Optional[str] = None,
    spec_name: str = "Default",
    cost_price_cents: Optional[Union[int, float, str]] = None,
    low_stock_threshold: Optional[int] = None,
    is_active: bool = True,
    brand_id: Optional[int] = None
) -> Product:
    """
    Create a new product with an initial guaranteed 'Default' variant.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Product name is required.")

    cents = _normalize_cents(price_cents)
    cost_cents = _normalize_cents(cost_price_cents) if cost_price_cents is not None else None

    product = Product(
        name=clean_name,
        category_id=category_id,
        brand_id=brand_id,
        description=(description or "").strip() if description else None,
        image=(image or "").strip() if image else None,
        is_active=is_active,
        created_at=utc_now()
    )
    db.session.add(product)
    db.session.flush()  # Obtain product.id

    initial_sku = (sku or "").strip()
    if not initial_sku:
        initial_sku = f"PROD-{product.id}-DEF"

    variant = ProductVariant(
        product_id=product.id,
        sku=initial_sku,
        spec_name=(spec_name or "Default").strip(),
        price_cents=cents,
        cost_price_cents=cost_cents,
        stock=max(0, int(stock)),
        low_stock_threshold=low_stock_threshold,
        is_active=True
    )
    db.session.add(variant)
    db.session.commit()
    return product


def update_product(
    product_id: int,
    name: Optional[str] = None,
    category_id: Optional[int] = None,
    description: Optional[str] = None,
    image: Optional[str] = None,
    is_active: Optional[bool] = None,
    brand_id: Union[Optional[int], object] = _UNSET
) -> Optional[Product]:
    """
    Update top-level product attributes.
    """
    product = db.session.get(Product, product_id)
    if not product:
        return None

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Product name cannot be empty.")
        product.name = clean_name

    if category_id is not None:
        product.category_id = category_id

    if brand_id is not _UNSET:
        product.brand_id = brand_id

    if description is not None:
        product.description = description.strip() if description else None

    if image is not None:
        product.image = image.strip() if image else None

    if is_active is not None:
        product.is_active = bool(is_active)

    db.session.commit()
    return product


def delete_product(product_id: int) -> bool:
    """
    Delete a product and all its cascade-linked variants.
    """
    product = db.session.get(Product, product_id)
    if not product:
        return False

    db.session.delete(product)
    db.session.commit()
    return True


# ==========================================
# 2. Variant Queries & Management
# ==========================================

def get_variant_by_id(variant_id: int) -> Optional[ProductVariant]:
    """
    Fetch a single variant by primary key ID.
    """
    return db.session.get(ProductVariant, variant_id)


def get_variant_by_sku(sku: str) -> Optional[ProductVariant]:
    """
    Fetch a variant by unique SKU.
    """
    if not sku:
        return None
    return ProductVariant.query.filter_by(sku=sku.strip()).first()


def get_variants_by_product_id(product_id: int, only_active: bool = False) -> List[ProductVariant]:
    """
    Fetch all variants linked to a product ID.
    """
    query = ProductVariant.query.filter(ProductVariant.product_id == product_id)
    if only_active:
        query = query.filter(ProductVariant.is_active == True)
    return query.order_by(ProductVariant.id.asc()).all()


def create_variant(
    product_id: int,
    sku: str,
    spec_name: str = "Default",
    price_cents: Union[int, float, str] = 0,
    stock: int = 0,
    cost_price_cents: Optional[Union[int, float, str]] = None,
    low_stock_threshold: Optional[int] = None,
    is_active: bool = True
) -> ProductVariant:
    """
    Create a new variant for an existing product.
    """
    product = db.session.get(Product, product_id)
    if not product:
        raise ProductNotFoundError(f"Product {product_id} not found.")

    clean_sku = (sku or "").strip()
    if not clean_sku:
        raise ValueError("Variant SKU is required.")

    existing = ProductVariant.query.filter_by(sku=clean_sku).first()
    if existing:
        raise ValueError(f"SKU '{clean_sku}' already exists.")

    cents = _normalize_cents(price_cents)
    cost_cents = _normalize_cents(cost_price_cents) if cost_price_cents is not None else None

    variant = ProductVariant(
        product_id=product_id,
        sku=clean_sku,
        spec_name=(spec_name or "Default").strip(),
        price_cents=cents,
        cost_price_cents=cost_cents,
        stock=max(0, int(stock)),
        low_stock_threshold=low_stock_threshold,
        is_active=bool(is_active)
    )
    db.session.add(variant)
    db.session.commit()
    return variant


def update_variant(
    variant_id: int,
    sku: Optional[str] = None,
    spec_name: Optional[str] = None,
    price_cents: Optional[Union[int, float, str]] = None,
    cost_price_cents: Optional[Union[int, float, str]] = None,
    stock: Optional[int] = None,
    low_stock_threshold: Optional[int] = None,
    is_active: Optional[bool] = None
) -> Optional[ProductVariant]:
    """
    Update variant attributes (SKU, spec, price, stock, threshold, active state).
    """
    variant = db.session.get(ProductVariant, variant_id)
    if not variant:
        raise VariantNotFoundError(f"Variant {variant_id} not found.")

    if sku is not None:
        clean_sku = sku.strip()
        if not clean_sku:
            raise ValueError("Variant SKU cannot be empty.")
        existing = ProductVariant.query.filter(
            ProductVariant.sku == clean_sku,
            ProductVariant.id != variant_id
        ).first()
        if existing:
            raise ValueError(f"SKU '{clean_sku}' already in use by another variant.")
        variant.sku = clean_sku

    if spec_name is not None:
        variant.spec_name = spec_name.strip()

    if price_cents is not None:
        variant.price_cents = _normalize_cents(price_cents)

    if cost_price_cents is not None:
        variant.cost_price_cents = _normalize_cents(cost_price_cents)

    if stock is not None:
        if int(stock) < 0:
            raise ValueError("Stock count cannot be negative.")
        variant.stock = int(stock)

    if low_stock_threshold is not None:
        variant.low_stock_threshold = int(low_stock_threshold)

    if is_active is not None:
        variant.is_active = bool(is_active)

    db.session.commit()
    return variant


def delete_variant(variant_id: int) -> bool:
    """
    Delete a variant. Ensures product retains at least one variant.
    """
    variant = db.session.get(ProductVariant, variant_id)
    if not variant:
        return False

    variant_count = ProductVariant.query.filter_by(product_id=variant.product_id).count()
    if variant_count <= 1:
        raise ValueError("Cannot delete the only variant of a product. Products must have at least one variant.")

    db.session.delete(variant)
    db.session.commit()
    return True


def update_stock(variant_id: int, new_stock: int) -> bool:
    """
    Directly update the stock count of a variant (for admin manual adjustment).
    """
    if int(new_stock) < 0:
        raise ValueError("Stock count cannot be negative.")

    variant = db.session.get(ProductVariant, variant_id)
    if not variant:
        return False

    variant.stock = int(new_stock)
    db.session.commit()
    return True


def get_low_stock_variants(threshold: Optional[int] = None) -> List[ProductVariant]:
    """
    Fetch all variants whose stock is at or below their low-stock threshold.
    """
    fallback = threshold if threshold is not None else _get_fallback_low_stock_threshold()
    all_variants = ProductVariant.query.filter(ProductVariant.is_active == True).all()
    low_stock = []
    for v in all_variants:
        thresh = v.low_stock_threshold if v.low_stock_threshold is not None else fallback
        if v.stock <= thresh:
            low_stock.append(v)
    return low_stock


def set_test_prices_cents(cents: Optional[int] = None) -> int:
    """
    Update all product variants in the database to test pricing: 1 cent ($0.01) or 2 cents ($0.02).
    If cents is None, alternates between 1 cent ($0.01) and 2 cents ($0.02) across all variants.
    Returns the total number of variants updated.
    """
    variants = ProductVariant.query.order_by(ProductVariant.id.asc()).all()
    for idx, v in enumerate(variants):
        if cents is not None:
            v.price_cents = max(1, int(cents))
        else:
            v.price_cents = 1 if (idx % 2 == 0) else 2
    db.session.commit()
    return len(variants)


# ==========================================
# 3. Concurrency & Inventory Decrement Contract
# ==========================================

def decrement_stock_atomic(variant_id: int, quantity: int) -> bool:
    """
    Contract:
    Performs a single atomic database update:
      UPDATE product_variants SET stock = stock - :qty WHERE id = :id AND stock >= :qty
    Check the affected rowcount (rowcount == 1).
    No with_for_update or manual lock is allowed, ensuring high-concurrency safety across SQLite and MySQL.

    Returns:
      bool: True if stock was decremented successfully, False if insufficient stock or variant not found.
    """
    if quantity <= 0:
        return False

    stmt = text(
        "UPDATE product_variants "
        "SET stock = stock - :qty "
        "WHERE id = :variant_id AND stock >= :qty"
    )
    result = db.session.execute(stmt, {"variant_id": variant_id, "qty": quantity})

    if result.rowcount != 1:
        db.session.rollback()
        return False

    db.session.commit()
    db.session.expire_all()

    # Check if variant has hit or fallen below low-stock threshold
    variant = db.session.get(ProductVariant, variant_id)
    if variant:
        thresh = (
            variant.low_stock_threshold
            if variant.low_stock_threshold is not None
            else _get_fallback_low_stock_threshold()
        )
        if variant.stock <= thresh:
            _notify_low_stock(variant, thresh)

    return True


def restore_stock(variant_id: int, quantity: int) -> bool:
    """
    Restores inventory when an order is cancelled or expires.

    Returns:
      bool: True if stock was restored, False otherwise.
    """
    if quantity <= 0:
        return False

    stmt = text(
        "UPDATE product_variants "
        "SET stock = stock + :qty "
        "WHERE id = :variant_id"
    )
    result = db.session.execute(stmt, {"variant_id": variant_id, "qty": quantity})

    if result.rowcount == 1:
        db.session.commit()
        return True

    db.session.rollback()
    return False


# ==========================================
# 4. Brand Management CRUD
# ==========================================

def _generate_unique_brand_slug(name: str, current_id: Optional[int] = None) -> str:
    """Generate a unique slug for a brand."""
    base_slug = slugify(name) or "brand"
    candidate = base_slug
    counter = 1
    while True:
        query = Brand.query.filter_by(slug=candidate)
        if current_id is not None:
            query = query.filter(Brand.id != current_id)
        if not query.first():
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


def get_all_brands() -> List[Brand]:
    """Fetch all brands ordered alphabetically by name."""
    return Brand.query.order_by(Brand.name.asc()).all()


def get_brand_by_id(brand_id: int) -> Optional[Brand]:
    """Fetch a single brand by its primary key ID."""
    return db.session.get(Brand, brand_id)


def get_brand_by_slug(slug: str) -> Optional[Brand]:
    """Fetch a brand by its unique URL slug."""
    if not slug:
        return None
    return Brand.query.filter_by(slug=slug.strip()).first()


def create_brand(
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    logo: Optional[str] = None,
    website: Optional[str] = None
) -> Brand:
    """
    Create a new brand. Auto-generates a unique slug if not provided.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Brand name is required.")

    existing_name = Brand.query.filter_by(name=clean_name).first()
    if existing_name:
        raise ValueError(f"Brand '{clean_name}' already exists.")

    if slug and slug.strip():
        clean_slug = slugify(slug)
        existing_slug = Brand.query.filter_by(slug=clean_slug).first()
        if existing_slug:
            raise ValueError(f"Brand slug '{clean_slug}' already exists.")
    else:
        clean_slug = _generate_unique_brand_slug(clean_name)

    brand = Brand(
        name=clean_name,
        slug=clean_slug,
        description=(description or "").strip() if description else None,
        logo=(logo or "").strip() if logo else None,
        website=(website or "").strip() if website else None,
        created_at=utc_now()
    )
    db.session.add(brand)
    db.session.commit()
    return brand


def update_brand(
    brand_id: int,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    logo: Optional[str] = None,
    website: Optional[str] = None
) -> Optional[Brand]:
    """
    Update brand attributes (name, slug, description, logo, website).
    """
    brand = db.session.get(Brand, brand_id)
    if not brand:
        return None

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Brand name cannot be empty.")
        existing = Brand.query.filter(Brand.name == clean_name, Brand.id != brand_id).first()
        if existing:
            raise ValueError(f"Brand name '{clean_name}' already in use.")
        brand.name = clean_name

    if slug is not None:
        clean_slug = slugify(slug)
        if not clean_slug:
            clean_slug = _generate_unique_brand_slug(brand.name, current_id=brand_id)
        existing = Brand.query.filter(Brand.slug == clean_slug, Brand.id != brand_id).first()
        if existing:
            raise ValueError(f"Brand slug '{clean_slug}' already in use.")
        brand.slug = clean_slug

    if description is not None:
        brand.description = description.strip() if description else None

    if logo is not None:
        brand.logo = logo.strip() if logo else None

    if website is not None:
        brand.website = website.strip() if website else None

    db.session.commit()
    return brand


def delete_brand(brand_id: int) -> bool:
    """
    CRITICAL ACCEPTANCE CRITERION:
    Deleting a brand MUST safely disassociate linked products by setting
    product.brand_id = None (NULL) BEFORE deleting the brand row,
    without cascading deletion of any products.
    """
    brand = db.session.get(Brand, brand_id)
    if not brand:
        return False

    # Disassociate all linked products safely (setting brand_id = NULL)
    Product.query.filter_by(brand_id=brand_id).update({Product.brand_id: None})
    db.session.flush()

    db.session.delete(brand)
    db.session.commit()
    return True


# ==========================================
# 5. Category Management CRUD
# ==========================================

def _generate_unique_category_slug(name: str, current_id: Optional[int] = None) -> str:
    """Generate a unique slug for a category."""
    base_slug = slugify(name) or "category"
    candidate = base_slug
    counter = 1
    while True:
        query = Category.query.filter_by(slug=candidate)
        if current_id is not None:
            query = query.filter(Category.id != current_id)
        if not query.first():
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


def get_all_categories() -> List[Category]:
    """Fetch all categories ordered alphabetically by name."""
    return Category.query.order_by(Category.name.asc()).all()


def get_category_by_id(category_id: int) -> Optional[Category]:
    """Fetch a single category by its primary key ID."""
    return db.session.get(Category, category_id)


def get_category_by_slug(slug: str) -> Optional[Category]:
    """Fetch a category by its unique URL slug."""
    if not slug:
        return None
    return Category.query.filter_by(slug=slug.strip()).first()


def create_category(name: str, slug: Optional[str] = None) -> Category:
    """
    Create a new category. Auto-generates a unique slug if not provided.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Category name is required.")

    existing_name = Category.query.filter_by(name=clean_name).first()
    if existing_name:
        raise ValueError(f"Category '{clean_name}' already exists.")

    if slug and slug.strip():
        clean_slug = slugify(slug)
        existing_slug = Category.query.filter_by(slug=clean_slug).first()
        if existing_slug:
            raise ValueError(f"Category slug '{clean_slug}' already exists.")
    else:
        clean_slug = _generate_unique_category_slug(clean_name)

    category = Category(name=clean_name, slug=clean_slug)
    db.session.add(category)
    db.session.commit()
    return category


def update_category(
    category_id: int,
    name: Optional[str] = None,
    slug: Optional[str] = None
) -> Optional[Category]:
    """
    Update category attributes (name, slug).
    """
    category = db.session.get(Category, category_id)
    if not category:
        return None

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Category name cannot be empty.")
        existing = Category.query.filter(Category.name == clean_name, Category.id != category_id).first()
        if existing:
            raise ValueError(f"Category name '{clean_name}' already in use.")
        category.name = clean_name

    if slug is not None:
        clean_slug = slugify(slug)
        if not clean_slug:
            clean_slug = _generate_unique_category_slug(category.name, current_id=category_id)
        existing = Category.query.filter(Category.slug == clean_slug, Category.id != category_id).first()
        if existing:
            raise ValueError(f"Category slug '{clean_slug}' already in use.")
        category.slug = clean_slug

    db.session.commit()
    return category


def delete_category(category_id: int, reassign_to_id: Optional[int] = None) -> bool:
    """
    Delete a category. If products are linked:
      - If reassign_to_id is provided, safely reassigns products to that category.
      - Otherwise, raises ValueError to prevent orphaned products.
    """
    category = db.session.get(Category, category_id)
    if not category:
        return False

    linked_count = Product.query.filter_by(category_id=category_id).count()
    if linked_count > 0:
        if not reassign_to_id:
            raise ValueError(
                f"Cannot delete category '{category.name}' because {linked_count} product(s) are linked to it. "
                "Please reassign those products first."
            )
        target_cat = db.session.get(Category, reassign_to_id)
        if not target_cat:
            raise ValueError(f"Target reassignment category {reassign_to_id} does not exist.")
        if target_cat.id == category_id:
            raise ValueError("Cannot reassign products to the same category being deleted.")

        Product.query.filter_by(category_id=category_id).update({Product.category_id: reassign_to_id})
        db.session.flush()

    db.session.delete(category)
    db.session.commit()
    return True
