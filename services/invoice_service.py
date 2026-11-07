"""
Invoice Service - Professional PDF invoice and receipt generation via ReportLab.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from extensions import db
from models.order import Order
from helpers.money import format_money
from helpers.time import to_local, utc_now
from config import Config


def generate_invoice_pdf(order_id: int) -> io.BytesIO:
    """
    Generates a high-quality, professional PDF invoice for the specified order.

    Args:
        order_id: The ID or order number of the order.

    Returns:
        io.BytesIO: In-memory binary buffer containing the PDF.
    """
    order = None
    if isinstance(order_id, int) or (isinstance(order_id, str) and order_id.isdigit()):
        order = db.session.get(Order, int(order_id))
    if not order:
        # Fallback check by order_number
        order = Order.query.filter_by(order_number=str(order_id)).first()
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    brand_style = ParagraphStyle(
        'BrandTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#4F46E5')  # Indigo
    )
    brand_sub = ParagraphStyle(
        'BrandSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748B')
    )
    invoice_title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=2,  # Right aligned
        textColor=colors.HexColor('#0F172A')
    )
    invoice_meta_style = ParagraphStyle(
        'InvoiceMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        alignment=2,
        textColor=colors.HexColor('#475569')
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1E293B')
    )
    body_text = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    story = []

    # Localized date string
    local_order_date = to_local(order.created_at)
    date_str = local_order_date.strftime("%B %d, %Y - %I:%M %p") if local_order_date else "N/A"

    # 1. Header Block (Brand on left, Invoice Details on right)
    header_data = [
        [
            Paragraph(f"<b>{getattr(Config, 'STORE_NAME', 'TechStore')}</b>", brand_style),
            Paragraph("<b>OFFICIAL INVOICE & RECEIPT</b>", invoice_title_style)
        ],
        [
            Paragraph("Computer Hardware & POS Solutions<br/>Phnom Penh, Kingdom of Cambodia", brand_sub),
            Paragraph(f"<b>Invoice #:</b> {order.order_number}<br/>"
                      f"<b>Date:</b> {date_str}<br/>"
                      f"<b>Status:</b> {order.status.upper()}<br/>"
                      f"<b>Payment:</b> {order.payment_method.upper()}", invoice_meta_style)
        ]
    ]

    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceBefore=5, spaceAfter=15))

    # 2. Bill To & Shipping Information
    customer_info = [
        [
            Paragraph("<b>BILLED TO & SHIPPING DESTINATION:</b>", section_heading),
            Paragraph("<b>STORE INFORMATION:</b>", section_heading)
        ],
        [
            Paragraph(f"<b>Customer:</b> {order.customer_name}<br/>"
                      f"<b>Email:</b> {order.email}<br/>"
                      f"<b>Phone:</b> {order.phone}<br/>"
                      f"<b>Address:</b> {order.address}", body_text),
            Paragraph(f"<b>Merchant:</b> {getattr(Config, 'STORE_NAME', 'TechStore')} Ltd.<br/>"
                      f"<b>Support:</b> support@techstore.com<br/>"
                      f"<b>Currency:</b> USD & KHR (Cambodian Riel)<br/>"
                      f"<b>Timezone:</b> {getattr(Config, 'STORE_TIMEZONE', 'Asia/Phnom_Penh')} (UTC+7)", body_text)
        ]
    ]

    info_table = Table(customer_info, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # 3. Itemized Products Table
    items_header = [
        Paragraph("#", table_header),
        Paragraph("Product & Specification", table_header),
        Paragraph("SKU", table_header),
        Paragraph("Qty", table_header),
        Paragraph("Unit Price", table_header),
        Paragraph("Line Total", table_header)
    ]
    table_rows = [items_header]

    for idx, item in enumerate(order.items, start=1):
        spec_text = f"<br/><font color='#64748B' size='7'>{item.spec_name}</font>" if item.spec_name else ""
        row = [
            Paragraph(str(idx), table_cell),
            Paragraph(f"<b>{item.product_name}</b>{spec_text}", table_cell),
            Paragraph(item.sku or "—", table_cell),
            Paragraph(str(item.qty), table_cell),
            Paragraph(format_money(item.unit_price_cents), table_cell),
            Paragraph(format_money(item.line_total_cents), table_cell_bold)
        ]
        table_rows.append(row)

    # If no line items are registered yet (fallback preview)
    if len(table_rows) == 1:
        table_rows.append([
            Paragraph("1", table_cell),
            Paragraph(f"Order #{order.order_number} Items Summary", table_cell),
            Paragraph("ORD-SUM", table_cell),
            Paragraph("1", table_cell),
            Paragraph(format_money(order.subtotal_cents), table_cell),
            Paragraph(format_money(order.subtotal_cents), table_cell_bold)
        ])

    items_table = Table(table_rows, colWidths=[25, 235, 80, 40, 80, 80])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # 4. Financial Totals & KHR Currency Estimation
    subtotal_fmt = format_money(order.subtotal_cents)
    discount_fmt = format_money(order.discount_cents)
    total_fmt = format_money(order.total_cents)

    # Dual currency conversion (Authoritative KHR / Secondary presentation)
    khr_rate = getattr(Config, 'KHR_RATE', 4000.0)
    total_dollars = order.total_cents / 100.0
    khr_estimate = int(round(total_dollars * khr_rate))
    khr_formatted = f"{khr_estimate:,} ៛"

    coupon_label = f"Promo Discount ({order.coupon_code})" if order.coupon_code else "Promotional Discount"

    summary_data = [
        [Paragraph("<b>Subtotal:</b>", body_text), Paragraph(subtotal_fmt, table_cell_bold)],
        [Paragraph(f"<b>{coupon_label}:</b>", body_text), Paragraph(f"-{discount_fmt}" if order.discount_cents > 0 else "$0.00", table_cell_bold)],
        [Paragraph("<b>Shipping / Delivery:</b>", body_text), Paragraph("Free", table_cell_bold)],
        [Paragraph("<b>Grand Total (USD):</b>", section_heading), Paragraph(f"<b>{total_fmt}</b>", brand_style)],
        [Paragraph("<b>National KHR Equivalent:</b>", body_text), Paragraph(f"<b>≈ {khr_formatted}</b>", section_heading)]
    ]

    summary_table = Table(summary_data, colWidths=[150, 100])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, 3), (-1, 3), 1, colors.HexColor('#4F46E5')),
    ]))

    # Wrap summary on right side
    outer_summary = Table([
        [
            Paragraph("<font color='#64748B' size='8'>Thank you for your order!<br/>"
                      "All orders are backed by our 4-hour cancellation grace period.<br/>"
                      "For warranty & support, visit techstore.com/support.</font>", body_text),
            summary_table
        ]
    ], colWidths=[290, 250])
    outer_summary.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(outer_summary)

    # Build the document
    doc.build(story)
    buffer.seek(0)
    return buffer
