from flask import request, redirect, url_for
from admin import admin_bp

@admin_bp.get('/login', endpoint='login')
def login():
    """
    302 Redirect to canonical /login preserving query parameters.
    Does not display form or process POST.
    """
    args = request.args.to_dict()
    return redirect(url_for('front_bp.login', **args))

@admin_bp.get('/register', endpoint='register')
def register():
    """
    302 Redirect to canonical /register preserving query parameters.
    Does not display form or process POST.
    """
    args = request.args.to_dict()
    return redirect(url_for('front_bp.register', **args))

@admin_bp.get('/logout', endpoint='logout')
def logout():
    """
    GET /admin/logout redirects to home page without logging anyone out.
    Logout requires POST /logout with CSRF protection.
    """
    return redirect(url_for('front_bp.home'))
    
