import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import app as flask_app
from extensions import db as _db
from models.user import User
from werkzeug.security import generate_password_hash

@pytest.fixture
def app():
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
    })

    # Isolate test suite from instance/mydb.sqlite3 using an in-memory SQLite engine with StaticPool
    mem_engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )

    with flask_app.app_context():
        sa_state = flask_app.extensions['sqlalchemy']
        orig_engine = sa_state.engines.get(None)
        sa_state.engines[None] = mem_engine

        # Section I: Test Safety Check - fail immediately if active engine is not in-memory SQLite
        active_url = str(_db.engine.url)
        if not (active_url.startswith('sqlite') and (':memory:' in active_url or 'memory' in active_url)):
            sa_state.engines[None] = orig_engine
            pytest.fail(f"TEST SAFETY VIOLATION: Active database engine is not in-memory SQLite! URL: {active_url}")

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
        sa_state.engines[None] = orig_engine

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
