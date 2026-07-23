import os
import glob
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS  # ⚠️ Necesario para que Vue y Flask conversen
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Importamos los modelos y funciones de BD (NUEVO: Se agregó VicidialConfig)
from config.database import db, User, LayoutConfig, VicidialConfig, init_db_and_admins

# IMPORTANTE: Importamos las nuevas funciones del extractor
from core.extractor import ejecutar_extraccion_hites, tarea_recolector_nocturno, tarea_inyector_semanal

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

# ACTUALIZADO: Habilitamos CORS para el nuevo puerto 8088
CORS(app, supports_credentials=True, origins=["http://172.26.10.200:8088", "http://localhost:8088"])

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
# CEREBRO AUTOMÁTICO (SCHEDULER)
# ==========================================
scheduler = BackgroundScheduler()

def actualizar_cronogramas():
    """Lee la base de datos y reprograma los inyectores FTP según lo configurado en el Panel Vue"""
    with app.app_context():
        # 1. Limpiamos los trabajos FTP anteriores por si cambiaste la hora en el panel
        for job in scheduler.get_jobs():
            if job.id.startswith('ftp_inyector_'):
                job.remove()
                
        # 2. Buscamos todas las configuraciones de mandantes guardadas
        layouts = LayoutConfig.query.all()
        for layout in layouts:
            cliente = layout.cliente
            datos = layout.columnas if isinstance(layout.columnas, dict) else {}
            sftp = datos.get('sftp', {})
            
            dia_str = sftp.get('dia', 'Viernes')
            hora_str = sftp.get('hora', '21:00')
            
            # Traductor de días del Panel Vue a formato Cron del Servidor
            dias_map = {
                'Lunes': 'mon', 'Martes': 'tue', 'Miercoles': 'wed',
                'Jueves': 'thu', 'Viernes': 'fri', 'Diario': 'mon-fri'
            }
            dia_cron = dias_map.get(dia_str, 'fri')
            
            try:
                hora, minuto = hora_str.split(':')
                job_id = f'ftp_inyector_{cliente}'
                
                # Agregamos el trabajo inyector al reloj interno
                scheduler.add_job(
                    func=tarea_inyector_semanal,
                    trigger=CronTrigger(day_of_week=dia_cron, hour=hora, minute=minuto),
                    args=[cliente],
                    id=job_id,
                    replace_existing=True
                )
                print(f"⏰ [RELOJ] Inyección de {cliente.upper()} programada: {dia_str} a las {hora_str}")
            except Exception as e:
                print(f"❌ [RELOJ] Error programando {cliente}: {e}")

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

# 4. ACTUALIZADO: Pide la configuración de la Campaña y SQL dinámicamente
@app.route('/api/layout/<cliente>', methods=['GET'])
@login_required
def obtener_layout(cliente):
    layout = LayoutConfig.query.filter_by(cliente=cliente).first()
    
    if layout:
        datos = layout.columnas if isinstance(layout.columnas, dict) else {}
        
        prefijo = datos.get("prefijo_campana", "")
        sql = datos.get("consulta_sql", "SELECT * FROM gestiones_raw;")
        sftp = datos.get("sftp", {"dia": "Viernes", "hora": "21:00", "ruta": "in/gestiones/mes_año"})
        
        return jsonify({
            "success": True, 
            "prefijo_campana": prefijo,
            "consulta_sql": sql,
            "sftp": sftp
        }), 200
    else:
        return jsonify({
            "success": True, 
            "prefijo_campana": "",
            "consulta_sql": "SELECT * FROM gestiones_raw;",
            "sftp": {"dia": "Viernes", "hora": "21:00", "ruta": "in/gestiones/mes_año"}
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
# RUTA DEL CONSTRUCTOR DE LAYOUTS DINÁMICO Y SFTP
# ==========================================

# 6. ACTUALIZADO: Guarda prefijo SQL y configuración de SFTP
@app.route('/api/layout/<cliente>/guardar', methods=['POST'])
@login_required
def guardar_layout(cliente):
    data = request.get_json()
    
    # Extraemos la nueva estructura de datos (Prefijo, SQL y SFTP)
    prefijo = data.get('prefijo_campana', '')
    sql = data.get('consulta_sql', '')
    config_sftp = data.get('sftp', {})
    
    # Empaquetamos todo
    paquete_final = {
        "prefijo_campana": prefijo,
        "consulta_sql": sql,
        "sftp": config_sftp
    }
    
    try:
        layout_existente = LayoutConfig.query.filter_by(cliente=cliente).first()
        
        if layout_existente:
            layout_existente.columnas = paquete_final
            print(f"🔄 Actualizando Motor SQL y SFTP en la BD para el cliente: {cliente}")
        else:
            nuevo_layout = LayoutConfig(cliente=cliente, columnas=paquete_final)
            db.session.add(nuevo_layout)
            print(f"💾 Creando nuevo Motor SQL y SFTP en la BD para el cliente: {cliente}")
            
        db.session.commit()
        
        # ¡NUEVA MAGIA!: Actualizamos el reloj interno en tiempo real sin reiniciar el servidor
        actualizar_cronogramas()
        
        return jsonify({
            "success": True, 
            "message": f"¡Motor SQL y SFTP para {cliente.upper()} guardado con éxito!"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al guardar en base de datos: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"Error interno en la BD: {str(e)}"
        }), 500

# ==========================================
# NUEVAS RUTAS: CREDENCIALES DE VICIDIAL
# ==========================================

# 7. Obtener las credenciales guardadas
@app.route('/api/config/vicidial', methods=['GET'])
@login_required
def get_vicidial_config():
    config = VicidialConfig.query.first()
    if config:
        return jsonify({
            "success": True, 
            "url": config.url, 
            "username": config.username, 
            "password": config.password
        }), 200
    
    return jsonify({"success": True, "url": "", "username": "", "password": ""}), 200

# 8. Guardar o actualizar las credenciales
@app.route('/api/config/vicidial/guardar', methods=['POST'])
@login_required
def save_vicidial_config():
    data = request.get_json()
    try:
        config = VicidialConfig.query.first()
        if config:
            config.url = data.get('url', '')
            config.username = data.get('username', '')
            config.password = data.get('password', '')
        else:
            nueva_config = VicidialConfig(
                url=data.get('url', ''), 
                username=data.get('username', ''), 
                password=data.get('password', '')
            )
            db.session.add(nueva_config)
            
        db.session.commit()
        print("💾 Credenciales de Vicidial guardadas exitosamente.")
        return jsonify({"success": True, "message": "Credenciales de Vicidial guardadas."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al guardar credenciales en BD: {str(e)}")
        return jsonify({"success": False, "message": f"Error BD: {str(e)}"}), 500

# ==========================================
# NUEVA RUTA: DESCARGAR ARCHIVO INYECTADO
# ==========================================

# 9. Descargar el último archivo procesado del cliente
@app.route('/api/descargar-ultimo/<cliente>', methods=['GET'])
@login_required
def descargar_ultimo(cliente):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        download_dir = os.path.join(base_dir, "downloads")
        
        # Buscar el archivo más reciente que coincida con el mandante (Ej: HITES_GESTIONES_*.csv)
        patron_busqueda = os.path.join(download_dir, f"{cliente.upper()}_GESTIONES_*.csv")
        archivos_encontrados = glob.glob(patron_busqueda)
        
        if not archivos_encontrados:
            return jsonify({"success": False, "message": "No hay archivos generados para descargar. Ejecuta el robot primero."}), 404
            
        # Obtenemos el archivo creado más recientemente
        ultimo_archivo = max(archivos_encontrados, key=os.path.getctime)
        
        return send_file(ultimo_archivo, as_attachment=True)
    
    except Exception as e:
        print(f"❌ Error al intentar descargar el archivo: {str(e)}")
        return jsonify({"success": False, "message": f"Error interno: {str(e)}"}), 500

# ==========================================
# INICIO DEL SERVIDOR Y CRONOGRAMAS
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        # 1. Tarea Fija: Descarga de Vicidial todos los días a las 02:00 AM
        scheduler.add_job(
            func=tarea_recolector_nocturno,
            trigger=CronTrigger(hour=2, minute=0),
            id='recolector_nocturno_diario',
            replace_existing=True
        )
        print("⏰ [RELOJ] Recolector Nocturno programado a las 02:00 AM todos los días.")
        
        # 2. Leer la BD para cargar las inyecciones FTP configuradas
        actualizar_cronogramas()
        
        # 3. Arrancar el reloj en segundo plano
        scheduler.start()
        
    app.run(host='0.0.0.0', port=5000)