from flask import Blueprint

api_bp = Blueprint('api_bp', __name__, template_folder='templates')

from api import user
from api import product
from api import auth
