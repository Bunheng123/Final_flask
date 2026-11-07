import sys
from flask import Flask, url_for, render_template, request, jsonify
from config import Config
from extensions import db, migrate, limiter, csrf , cors
from helpers.upload import (
    save_user_image,
    delete_profile_image,
    allowed_file,
    generate_image_names,
    get_thumb_name,
    UPLOAD_DIR,
    ALLOWED_EXT,
)
from bakong_khqr import KHQR

# If run directly as __main__, register 'app' in sys.modules for backwards compatibility
if __name__ == '__main__':
    sys.modules['app'] = sys.modules['__main__']

app = Flask(__name__)
# Database and app configuration (including SECRET_KEY, UPLOAD_DIR, etc.)
app.config.from_object(Config)

# Extensions
db.init_app(app)
migrate.init_app(app, db)
limiter.init_app(app)
csrf.init_app(app)
## CORS
cors.init_app(
    app,
    resources={
        r"/api/*": {"origins": "http://localhost:4200"}
    }
)

# Background Scheduler
from jobs import init_scheduler
init_scheduler(app)

# Load Models
import models

# Jinja template globals
app.jinja_env.globals['get_thumb_name'] = get_thumb_name

# URL build error handler for seamless endpoint compatibility across blueprints
def handle_build_error(error, endpoint, values):
    for bp_name in ('admin_bp', 'front_bp', 'api_bp'):
        prefixed = f"{bp_name}.{endpoint}"
        if prefixed in app.view_functions:
            return url_for(prefixed, **values)
    return None

app.url_build_error_handlers.append(handle_build_error)

# Register blueprints
from front import front_bp
from admin import admin_bp
from api import api_bp

app.register_blueprint(front_bp, url_prefix="/")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(api_bp, url_prefix="/api")
csrf.exempt(api_bp)

# Error handlers
from errors import register_error_handlers
register_error_handlers(app)

# CLI Commands
import click
from services.auth_service import create_admin_user

@app.cli.command('create-admin')
@click.option('--username', prompt=True, help='Admin username')
@click.option('--email', prompt=True, help='Admin email address')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Admin password')
def create_admin(username, email, password):
    """CLI command to create a new admin user."""
    try:
        user = create_admin_user(username, email, password)
        click.echo(f"Admin user '{user.username}' ({user.email}) created successfully.")
    except Exception as e:
        click.echo(f"Error creating admin user: {e}", err=True)




if __name__ == '__main__':
    app.run(debug=True)
