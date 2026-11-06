from flask import render_template, session, redirect, url_for
from admin import admin_bp
from extensions import limiter

@admin_bp.get('/dashboard', endpoint='dashboard')
@admin_bp.get('/', endpoint='dashboard_root')
@limiter.limit("10 per minute")# able to refresh 10 times per minute
def dashboard():
    module = 'dashboard'

    if not session.get('is_login'):
        return redirect(url_for('front_bp.login', next=url_for('admin_bp.dashboard')))

    return render_template('admin/dashboard/dashboard.html', module=module)