from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from app.installer import backend, frontend, middleware, ncache
from app.installer.precheck import run_prereq_check

main = Blueprint('main', __name__)

# ---------------------------
# Dashboard (muestra selector.html)
# ---------------------------
@main.route('/')
def selector():
    return render_template('selector.html')

# ---------------------------
# BackEnd
# ---------------------------
@main.route('/backend')
def backend_form():
    return render_template('install_backend.html')

@main.route('/install/backend', methods=['POST'])
def install_backend():
    result = backend.run_backend_installation(request.form, request.files)
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

# ---------------------------
# Selector de producto
# ---------------------------
@main.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# ---------------------------
# Página “en construcción” para Citas
# (cambia el nombre si tu template real es en_construccion.html)
# ---------------------------
@main.route('/citas')
def citas_soon():
    return render_template('construccion.html')

# ---------------------------
# Pre-check de requisitos
# ---------------------------
@main.route('/precheck/<product>')
def precheck_view(product):
    if product.lower() == 'citas':
        return redirect(url_for('main.citas_soon'))
    return render_template('precheck.html', product=product)

@main.route('/api/precheck')
def api_precheck():
    product = request.args.get('product', 'eflow')
    result = run_prereq_check(product)
    return jsonify(result)

# ---------------------------
# Continuar a Dashboard tras precheck
# ---------------------------
@main.route('/continuar/eflow')
def continuar_eflow():
    # Lo llevamos al dashboard (que hoy muestra el selector)
    return redirect(url_for('main.dashboard'))



