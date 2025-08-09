from flask import Flask
from app.routes import main

def create_app():
    app = Flask(__name__, template_folder='template', static_folder='static')  # asegúrate que busca en app/template
    app.register_blueprint(main)
    return app
