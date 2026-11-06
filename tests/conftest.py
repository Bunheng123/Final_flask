import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pytest
from app import app as flask_app
from extensions import db as _db
from models.user import User
from werkzeug.security import generate_password_hash

@pytest.fixture
def app():
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
    })

    with flask_app.app_context():
        _db.create_all()

        # Seed test admin user and standard user for permission tests
        admin_user = User(
            username='test_admin',
            email='admin@techstore.test',
            password=generate_password_hash('password123'),
            role='admin'
        )
        regular_user = User(
            username='test_user',
            email='user@techstore.test',
            password=generate_password_hash('password123'),
            role='user'
        )
        _db.session.add(admin_user)
        _db.session.add(regular_user)
        _db.session.commit()

        yield flask_app

        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
