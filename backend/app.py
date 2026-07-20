import os
from flask import Flask, jsonify, request
from flask_cors import CORS  # ⚠️ Necesario para que Vue y Flask conversen
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash

# Importamos los modelos y funciones de BD
from config.database import db, User, LayoutConfig, init_db_and_admins
from core.extractor import ejecutar_extraccion_hites

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE SEGURIDAD Y BASE DE DATOS
# ==========================================
app.config['SECRET_KEY'] = 'super-llave-secreta-etl-hites-2026'

DB_USER = os.getenv('DB_USER', 'etl_admin')
DB_PASS = os.getenv('DB_PASSWORD', 'etl_password_segura_2026')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'central_etl_db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Habilitamos CORS permitiendo credenciales (cookies de sesión) desde Vue
CORS(app, supports_credentials=True, origins=["http://172.26.10.200:5173", "http://localhost:5173"])

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

# Como somos una API, si alguien sin sesión intenta entrar, devolvemos un JSON (Error 401)
@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"success": False, "message": "Acceso denegado. Debes iniciar sesión."}), 401

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

init_db_and_admins(app)

# ==========================================
# RUTAS API (PUNTOS DE CONEXIÓN PARA VUE)
# ==========================================

# 1. Ruta para verificar si el usuario tiene sesión activa
@app.route('/api/status', methods=['GET'])
@login_required 
def status():
    return jsonify({
        "success": True, 
        "user": current_user.username,
        "message": "Sesión activa y backend funcionando."
    })

# 2. Ruta para iniciar sesión desde Vue
@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute") 
def login():
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"success": False, "message": "Faltan credenciales."}), 400

    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        return jsonify({
            "success": True, 
            "message": f"¡Bienvenido {username}!",
            "user": username
        })
    else:
        return jsonify({"success": False, "message": "Usuario o contraseña incorrectos."}), 401

# 3. Ruta para cerrar sesión
@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"success": True, "message": "Sesión cerrada correctamente."})

# 4. ACTUALIZADO: Pide la configuración del layout de CUALQUIER cliente dinámicamente
@app.route('/api/layout/<cliente>', methods=['GET'])
@login_required
def obtener_layout(cliente):
    layout = LayoutConfig.query.filter_by(cliente=cliente).first()
    
    if layout:
        return jsonify({
            "success": True, 
            "columnas": layout.columnas
        }), 200
    else:
        return jsonify({
            "success": True, 
            "columnas": []
        }), 200

# ==========================================
# RUTAS DEL MOTOR ETL
# ==========================================

# 5. Ruta para que Vue dispare el Robot Hites
@app.route('/api/ejecutar-etl', methods=['POST'])
@login_required
def ejecutar_etl():
    print("¡BIP BOP! Orden recibida vía API. Despertando al Robot v29.0...")
    exito, mensaje = ejecutar_extraccion_hites()
    
    if exito:
        return jsonify({"success": True, "message": mensaje}), 200
    else:
        return jsonify({"success": False, "message": mensaje}), 500

# ==========================================
# RUTA DEL CONSTRUCTOR DE LAYOUTS DINÁMICO
# ==========================================

# 6. ACTUALIZADO: Guarda o actualiza el layout de CUALQUIER cliente en PostgreSQL
@app.route('/api/layout/<cliente>/guardar', methods=['POST'])
@login_required
def guardar_layout(cliente):
    data = request.get_json()
    
    if not data or 'columnas' not in data:
        return jsonify({"success": False, "message": "No se enviaron columnas válidas"}), 400
        
    columnas_nuevas = data['columnas']
    
    try:
        # Buscamos si ya existía un registro previo para este cliente específico
        layout_existente = LayoutConfig.query.filter_by(cliente=cliente).first()
        
        if layout_existente:
            layout_existente.columnas = columnas_nuevas
            print(f"🔄 Actualizando layout en la BD para el cliente: {cliente}")
        else:
            nuevo_layout = LayoutConfig(cliente=cliente, columnas=columnas_nuevas)
            db.session.add(nuevo_layout)
            print(f"💾 Creando nuevo registro de layout en la BD para el cliente: {cliente}")
            
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"¡Configuración de Layout para {cliente.upper()} guardada con éxito!"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al guardar en base de datos: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"Error interno en la BD: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)