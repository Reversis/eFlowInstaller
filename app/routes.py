from flask import Blueprint, render_template, request
from app.installer import backend, frontend, middleware, ncache

main = Blueprint('main', __name__)

# ---------------------------
# Página principal (Dashboard)
# ---------------------------
@main.route('/')
def dashboard():
    return render_template('dashboard.html')

# ---------------------------
# BackEnd
# ---------------------------
@main.route('/backend')
def backend_form():
    return render_template('install_backend.html')

@main.route('/install/backend', methods=['POST'])
def install_backend():
    result = backend.run_backend_installation(request.form)
    return f"<pre>{result['output']}</pre><br><a href='/{result['log_file']}'>Descargar Log</a>"

# ---------------------------
# FrontEnd
# ---------------------------
@main.route('/frontend')
def frontend_form():
    return render_template('install_frontend.html')

@main.route('/install/frontend', methods=['POST'])
def install_frontend():
    result = frontend.run_frontend_installation(request.form)
    return f"<pre>{result['output']}</pre><br><a href='/{result['log_file']}'>Descargar Log</a>"

# ---------------------------
# MiddleWare
# ---------------------------
@main.route('/middleware')
def middleware_form():
    return render_template('install_middleware.html')

@main.route('/install/middleware', methods=['POST'])
def install_middleware():
    result = middleware.run_middleware_installation(request.form)
    return f"<pre>{result['output']}</pre><br><a href='/{result['log_file']}'>Descargar Log</a>"

# ---------------------------
# NCache
# ---------------------------
@main.route('/ncache')
def ncache_form():
    return render_template('install_ncache.html')

@main.route('/install/ncache', methods=['POST'])
def install_ncache():
    result = ncache.run_ncache_installation(request.form)
    return f"<pre>{result['output']}</pre><br><a href='/{result['log_file']}'>Descargar Log</a>"
