"""
Services package containing business logic across workstreams.
Routes in front/ and admin/ should remain thin and delegate domain operations to these services.
"""
from services import auth_service, email_service, stock_service, order_service, coupon_service, report_service

