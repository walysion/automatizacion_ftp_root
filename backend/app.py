import os
import glob
import io
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS  # ⚠️ Necesario para que Vue y Flask conversen
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Importamos los modelos y funciones de BD
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
# CEREBRO AUTOMÁTICO (SCHEDULER Y ORQUESTADOR HÍBRIDO)
# ==========================================
scheduler = BackgroundScheduler()

def orquestador_maestro(cliente, dia_inicio_ciclo=5, tipo_extraccion='semanal'):
    """
    EL MODELO HÍBRIDO INTELIGENTE:
    Puede actuar como "Bola de Nieve Semanal" o como "Transaccional Diario Puro"
    dependiendo del interruptor maestro configurado en la base de datos.
    """
    print(f"🚀 [ORQUESTADOR] Iniciando proceso automático para {cliente.upper()} en modo: {tipo_extraccion.upper()}")
    
    hoy = datetime.now()
    hoy_weekday = hoy.weekday() # Lunes = 0, Domingo = 6
    fecha_fin = hoy.strftime("%Y-%m-%d")
    
    # Lógica de decisión
    if tipo_extraccion == 'diario':
        # MODO DIARIO PURO: Solo el día de hoy
        fecha_inicio = hoy.strftime("%Y-%m-%d")
        print(f"🧠 [CEREBRO DIARIO] Extrayendo exclusivamente el día actual.")
    
    else:
        # MODO SEMANAL (Bola de Nieve): Calcula días de retroceso
        dias_retroceso = (hoy_weekday - dia_inicio_ciclo) % 7
        fecha_inicio = (hoy - timedelta(days=dias_retroceso)).strftime("%Y-%m-%d")
        print(f"🧠 [CEREBRO SEMANAL] Hoy es el día {hoy_weekday}. El ciclo inicia el día {dia_inicio_ciclo}.")
        print(f"🧠 [CEREBRO SEMANAL] La calculadora determinó ir {dias_retroceso} días hacia el pasado.")

    print(f"📅 [ORQUESTADOR] Rango de extracción definitivo: {fecha_inicio} al {fecha_fin}")
    
    # Enviar al Recolector a buscar los datos a Vicidial
    exito_rec, msg_rec = tarea_recolector_nocturno(start_date=fecha_inicio, end_date=fecha_fin)
    
    if not exito_rec:
        print(f"❌ [ORQUESTADOR] Operación abortada. Falló la recolección: {msg_rec}")
        return False
        
    print(f"✅ [ORQUESTADOR] Recolección consolidada con éxito. Levantando Inyector FTP...")
    
    # Si la recolección fue exitosa, inyectar el consolidado al FTP
    # Al ser el automático, le pasamos la fecha de fin (hoy) como referencia
    exito_iny = tarea_inyector_semanal(cliente, fecha_lote=fecha_fin)
    
    if exito_iny:
        print(f"🏆 [ORQUESTADOR] ¡Éxito total! Archivo consolidado de {cliente.upper()} inyectado correctamente.")
        return True
    else:
        print(f"❌ [ORQUESTADOR] La recolección terminó, pero el envío al FTP falló.")
        return False

def actualizar_cronogramas():
    """Lee la base de datos y reprograma el ORQUESTADOR según lo configurado en el Panel Vue"""
    with app.app_context():
        # Limpiamos los trabajos anteriores
        for job in scheduler.get_jobs():
            if job.id.startswith('etl_maestro_'):
                job.remove()
                
        # Buscamos todas las configuraciones
        layouts = LayoutConfig.query.all()
        for layout in layouts:
            cliente = layout.cliente
            datos = layout.columnas if isinstance(layout.columnas, dict) else {}
            sftp = datos.get('sftp', {})
            
            dia_str = sftp.get('dia', 'fri')
            hora_str = sftp.get('hora', '21:00')
            
            # Rescatamos variables clave
            dia_inicio_ciclo = int(sftp.get('dia_inicio_ciclo', 5))
            tipo_extraccion = sftp.get('tipo_extraccion', 'semanal') # Por defecto mantiene el sistema antiguo
            
            # Traductor exacto para compatibilidad
            dias_map = {
                'Todos los días LUNES': 'mon',
                'Todos los días MARTES': 'tue',
                'Todos los días MIÉRCOLES': 'wed',
                'Todos los días JUEVES': 'thu',
                'Todos los días VIERNES': 'fri',
                'Todos los días SÁBADO': 'sat',
                'Todos los días DOMINGO': 'sun',
                'Todos los días (L-V)': 'mon-fri',
                'Todos los días (L-D)': 'mon-sun',
                'Diario': 'mon-sun'
            }
            
            dia_cron = dias_map.get(dia_str, dia_str)
            
            try:
                hora, minuto = hora_str.split(':')
                job_id = f'etl_maestro_{cliente}'
                
                # Agregamos el Orquestador al reloj
                scheduler.add_job(
                    func=orquestador_maestro,
                    trigger=CronTrigger(day_of_week=dia_cron, hour=hora, minute=minuto),
                    args=[cliente, dia_inicio_ciclo, tipo_extraccion],
                    id=job_id,
                    replace_existing=True
                )
                print(f"⏰ [RELOJ] Orquestador ETL para {cliente.upper()} programado: {dia_cron} a las {hora_str} | Modo: {tipo_extraccion}")
            except Exception as e:
                print(f"❌ [RELOJ] Error programando {cliente}: {e}")

# ==========================================
# RUTAS API (PUNTOS DE CONEXIÓN PARA VUE)
# ==========================================

@app.route('/api/status', methods=['GET'])
@login_required 
def status():
    return jsonify({
        "success": True, 
        "user": current_user.username,
        "message": "Sesión activa y backend funcionando."
    })

@app.route('/api/server-time', methods=['GET'])
@login_required
def get_server_time():
    return jsonify({
        "success": True,
        "server_time": datetime.now().isoformat()
    })

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

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"success": True, "message": "Sesión cerrada correctamente."})

@app.route('/api/layout/<cliente>', methods=['GET'])
@login_required
def obtener_layout(cliente):
    layout = LayoutConfig.query.filter_by(cliente=cliente).first()
    
    if layout:
        datos = layout.columnas if isinstance(layout.columnas, dict) else {}
        
        prefijo = datos.get("prefijo_campana", "")
        sql = datos.get("consulta_sql", "SELECT * FROM gestiones;")
        
        # Inyectamos el valor por defecto si es que la BD es vieja y no lo tiene
        sftp = datos.get("sftp", {})
        if "dia_inicio_ciclo" not in sftp: sftp["dia_inicio_ciclo"] = 5
        if "tipo_extraccion" not in sftp: sftp["tipo_extraccion"] = "semanal"
        if "dia" not in sftp: sftp["dia"] = "fri"
        if "hora" not in sftp: sftp["hora"] = "21:00"
        if "ruta" not in sftp: sftp["ruta"] = "gestiones/mes_año"
        
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
            "consulta_sql": "SELECT * FROM gestiones;",
            "sftp": {"dia": "fri", "hora": "21:00", "ruta": "gestiones/mes_año", "dia_inicio_ciclo": 5, "tipo_extraccion": "semanal"}
        }), 200

# ==========================================
# RUTAS DEL MOTOR ETL Y HERRAMIENTAS MANUALES
# ==========================================

@app.route('/api/ejecutar-etl', methods=['POST'])
@login_required
def ejecutar_etl():
    print("¡BIP BOP! Orden recibida vía API. Despertando al Robot v29.0...")
    exito, mensaje = ejecutar_extraccion_hites()
    
    if exito:
        return jsonify({"success": True, "message": mensaje}), 200
    else:
        return jsonify({"success": False, "message": mensaje}), 500

# ⛏️ HERRAMIENTA A: EL MINERO (RESCATE DE VICIDIAL)
@app.route('/api/robot/rescate', methods=['POST'])
@login_required
def ejecutar_rescate():
    data = request.get_json()
    cliente = data.get('cliente', 'hites')
    fecha_inicio_str = data.get('fecha_inicio')
    fecha_fin_str = data.get('fecha_fin')

    if not fecha_inicio_str or not fecha_fin_str:
        return jsonify({"success": False, "message": "Faltan fechas."}), 400

    try:
        f_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        f_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        
        dias_totales = (f_fin - f_inicio).days
        
        if dias_totales < 0:
            return jsonify({"success": False, "message": "La fecha de inicio no puede ser mayor que la de fin."}), 400

        print(f"⛏️ [MINERO] Iniciando rescate para {cliente.upper()} desde {fecha_inicio_str} al {fecha_fin_str}")
        
        # EL BUCLE MAGISTRAL: Procesa día por día para no ahogar a Vicidial
        for i in range(dias_totales + 1):
            dia_actual = f_inicio + timedelta(days=i)
            dia_str = dia_actual.strftime('%Y-%m-%d')
            
            print(f"🔄 [MINERO] Extrayendo y procesando día: {dia_str}")
            
            # 1. Va a buscar los datos a Vicidial
            exito_rec, msg_rec = tarea_recolector_nocturno(start_date=dia_str, end_date=dia_str)
            
            if exito_rec:
                # 2. Si encontró datos, los inyecta. 
                # Le pasamos "fecha_lote" para que viaje en el tiempo y cree la carpeta del mes correcto
                tarea_inyector_semanal(cliente, fecha_lote=dia_str)
            else:
                print(f"⚠️ [MINERO] El día {dia_str} falló o no tenía datos: {msg_rec}")

        return jsonify({"success": True, "message": f"¡Rescate completado! Se procesaron los días del {fecha_inicio_str} al {fecha_fin_str}."}), 200

    except Exception as e:
        print(f"❌ Error en rescate: {e}")
        return jsonify({"success": False, "message": f"Error interno en rescate: {str(e)}"}), 500

# 📦 HERRAMIENTA B: LA BÓVEDA (EXPORTADOR HISTÓRICO MASIVO)
@app.route('/api/exportar-historico/<cliente>', methods=['GET'])
@login_required
def exportar_historico(cliente):
    inicio = request.args.get('inicio')
    fin = request.args.get('fin')
    
    if not inicio or not fin:
        return jsonify({"success": False, "message": "Faltan fechas"}), 400
        
    layout = LayoutConfig.query.filter_by(cliente=cliente).first()
    if not layout:
        return jsonify({"success": False, "message": "No hay configuración para este cliente"}), 404
        
    datos = layout.columnas if isinstance(layout.columnas, dict) else {}
    prefijo = datos.get("prefijo_campana", "")
    sql_usuario = datos.get("consulta_sql", "SELECT * FROM gestiones;")
    
    # Limpiamos el punto y coma final si el usuario lo puso, para evitar errores de sintaxis
    sql_usuario = sql_usuario.strip().rstrip(';')
    
    # EL TRUCO DE ARQUITECTURA: 
    # Creamos una "Tabla Virtual" (CTE) filtrada en tiempo real.
    # Así, cuando el SQL del usuario hace "FROM gestiones", lee solo los datos de esa fecha y campaña.
    consulta_final = f"""
    WITH gestiones AS (
        SELECT * FROM gestiones_raw 
        WHERE fecha >= '{inicio} 00:00:00' 
        AND fecha <= '{fin} 23:59:59'
        AND campana LIKE '{prefijo}%%'
    )
    {sql_usuario}
    """
    
    try:
        print(f"📦 [BÓVEDA] Extrayendo consolidado histórico de {cliente.upper()}...")
        
        # Usamos pandas para ejecutar el SQL directo en la base de datos y traer el resultado
        df = pd.read_sql(consulta_final, db.engine)
        
        # Convertimos el DataFrame a un CSV en memoria RAM (Súper rápido, sin tocar el disco duro)
        output = io.StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        
        # Enviamos el archivo flotando directo al navegador del usuario
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{cliente.upper()}_CONSOLIDADO_{inicio}_al_{fin}.csv'
        )
    except Exception as e:
        print(f"❌ Error exportando histórico: {e}")
        return jsonify({"success": False, "message": f"Error BD: {str(e)}"}), 500

# ==========================================
# RUTA DEL CONSTRUCTOR DE LAYOUTS DINÁMICO Y SFTP
# ==========================================

@app.route('/api/layout/<cliente>/guardar', methods=['POST'])
@login_required
def guardar_layout(cliente):
    data = request.get_json()
    
    prefijo = data.get('prefijo_campana', '')
    sql = data.get('consulta_sql', '')
    config_sftp = data.get('sftp', {})
    
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
# RUTAS: CREDENCIALES DE VICIDIAL
# ==========================================

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
# RUTA: DESCARGAR ARCHIVO INYECTADO
# ==========================================

@app.route('/api/descargar-ultimo/<cliente>', methods=['GET'])
@login_required
def descargar_ultimo(cliente):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        download_dir = os.path.join(base_dir, "downloads")
        
        patron_busqueda = os.path.join(download_dir, f"*GESTIONES_*.csv")
        archivos_encontrados = glob.glob(patron_busqueda)
        
        if not archivos_encontrados:
            return jsonify({"success": False, "message": "No hay archivos generados para descargar. Ejecuta el robot primero."}), 404
            
        ultimo_archivo = max(archivos_encontrados, key=os.path.getctime)
        
        return send_file(ultimo_archivo, as_attachment=True)
    
    except Exception as e:
        print(f"❌ Error al intentar descargar el archivo: {str(e)}")
        return jsonify({"success": False, "message": f"Error interno: {str(e)}"}), 500

# ==========================================
# INICIO DEL SERVIDOR Y CRONOGRAMAS
# ==========================================

with app.app_context():
    actualizar_cronogramas()

if not scheduler.running:
    scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)