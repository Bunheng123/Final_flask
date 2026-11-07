"""
Admin Accounting & Inventory Valuation Reports.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
from flask import render_template, request, Response, send_file
from admin import admin_bp
from services.report_service import (
    generate_sales_report,
    generate_inventory_valuation,
    export_sales_csv,
    export_sales_excel
)


@admin_bp.get('/reports', endpoint='admin_reports')
def admin_reports():
    """
    Render accounting dashboard with revenue totals, orders breakdown, and inventory valuation.
    """
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    sales = generate_sales_report(start_date, end_date)
    inventory = generate_inventory_valuation()

    return render_template(
        'admin/reports/reports.html',
        sales=sales,
        inventory=inventory,
        start_date=start_date,
        end_date=end_date,
        module='reports'
    )


@admin_bp.get('/reports/export-csv', endpoint='admin_export_csv')
def admin_export_csv():
    """
    Export sales records and financial summary as a CSV download.
    """
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    csv_data = export_sales_csv(start_date, end_date)
    filename = f"sales_report_{start_date or 'all'}_to_{end_date or 'latest'}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@admin_bp.get('/reports/export-excel', endpoint='admin_export_excel')
def admin_export_excel():
    """
    Export sales and inventory report as a multi-tab Excel workbook (.xlsx).
    """
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    excel_buffer = export_sales_excel(start_date, end_date)
    filename = f"accounting_report_{start_date or 'all'}_to_{end_date or 'latest'}.xlsx"

    return send_file(
        excel_buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )
