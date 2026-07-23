import os
import time
import glob
import logging
import traceback
import json
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Importamos nuestro nuevo inyector
from core.inyector import inyectar_ftp_resiliente

# =================================================================
# 1. CONFIGURACIÓN DE RUTAS Y BASE DE DATOS
# =================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "etl_nightly.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

# Conexión a PostgreSQL (usando las variables del Docker)
DB_USER = os.getenv('DB_USER', 'etl_admin')
DB_PASS = os.getenv('DB_PASSWORD', 'etl_password_segura_2026')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'central_etl_db')
POSTGRES_URI = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(POSTGRES_URI)

def log_print(msg, type="info"):
    """Imprime en consola y guarda en el log físico"""
    print(f"[ROBOT v29.0] {msg}")
    if type == "error":
        logging.error(msg)
    else:
        logging.info(msg)

def get_date_list(start_str, end_str):
    s = datetime.strptime(start_str, "%Y-%m-%d")
    e = datetime.strptime(end_str, "%Y-%m-%d")
    dates = []
    while s <= e:
        dates.append(s.strftime("%Y-%m-%d"))
        s += timedelta(days=1)
    return dates

# =================================================================
# TAREA A: EL RECOLECTOR NOCTURNO (Extrae y Guarda en BD Cruda)
# =================================================================
def tarea_recolector_nocturno(start_date=None, end_date=None):
    if not start_date or not end_date:
        # Por defecto, descarga el día anterior para no saturar
        ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = ayer
        end_date = ayer

    start_time_exec = time.time()
    total_rows_processed = 0
    driver = None
    date_list = get_date_list(start_date, end_date)

    vici_url, vici_user, vici_pass = "", "", ""
    try:
        with engine.connect() as conn:
            res_vici = conn.execute(text("SELECT url, username, password FROM vicidial_configs LIMIT 1")).fetchone()
            if res_vici:
                vici_url, vici_user, vici_pass = res_vici[0], res_vici[1], res_vici[2]
    except Exception as e:
        log_print(f"Error cargando credenciales de Vicidial: {e}", "error")

    if not vici_url or not vici_user or not vici_pass:
        return False, "❌ Faltan credenciales de Vicidial. Configúralas en el panel."

    login_url = vici_url
    if "index.php" in login_url:
        export_base_url = login_url.replace("index.php", "grilla/export_gestiones.php")
    else:
        export_base_url = "https://vicieffectiva.telexpress.cl/sistema_gestion/grilla/export_gestiones.php"

    log_print(f"Iniciando RECOLECTOR para {len(date_list)} días ({start_date} al {end_date})...")

    try:
        # Limpiar descargas previas crudas
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")):
            if not "GESTIONES" in f: # Protegemos los archivos inyectados finales
                try: os.remove(f)
                except: pass

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage") 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        prefs = {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.binary_location = "/usr/bin/chromium"
        
        service_obj = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service_obj, options=chrome_options)
        
        params = {'behavior': 'allow', 'downloadPath': DOWNLOAD_DIR}
        driver.execute_cdp_cmd('Page.setDownloadBehavior', params)
        wait = WebDriverWait(driver, 30)

        # LOGIN VICIDIAL
        log_print(f"Abriendo página de login: {login_url}")
        driver.get(login_url)
        time.sleep(2) 
        
        user_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        user_field.clear()
        user_field.send_keys(vici_user)
        driver.find_element(By.NAME, 'password').send_keys(vici_pass)
        
        try:
            driver.find_element(By.XPATH, '//input[@name="Submit2" and @value="Ingresar"]').click()
        except:
            driver.find_element(By.NAME, 'password').submit()
        
        time.sleep(3)
        log_print("Sesión iniciada correctamente.")

        # BUCLE ITERATIVO DE DESCARGA
        for target_date in date_list:
            log_print(f"Descargando datos crudos: Día {target_date}")

            direct_download_url = f"{export_base_url}?desde={target_date}&hasta={target_date}&rut=&valor_buscar=RUT&campana="
            driver.get(direct_download_url)
            time.sleep(3) 
            
            downloaded_file = None
            for _ in range(45): 
                files = [f for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")) if not f.endswith('.crdownload') and not "GESTIONES" in f]
                if files:
                    latest_file = max(files, key=os.path.getctime)
                    if os.path.getsize(latest_file) > 0:
                        downloaded_file = latest_file
                        break
                time.sleep(1)
                
            if not downloaded_file:
                log_print(f"No se generó reporte para {target_date}.", "error")
                continue

            # LIMPIEZA BÁSICA CON PANDAS
            try:
                df = pd.read_csv(downloaded_file, sep=None, engine='python', encoding='latin1', dtype=str, on_bad_lines='skip')
            except:
                df = pd.read_csv(downloaded_file, sep=',', encoding='utf-8', dtype=str, on_bad_lines='skip')

            if df is None or df.empty:
                continue

            df.columns = [str(c).lower().strip().replace(" ", "_").replace(".", "") for c in df.columns]
            
            # ¡SOLUCIÓN APLICADA!: Quitamos 'codigo' y 'gestion' para que no pise el 'status' (letras)
            renames = {
                'fono': 'telefono', 'telefono_cliente': 'telefono', 'phone_number': 'telefono',
                'rut': 'rut_cliente', 'status': 'cod_gestion',
                'fecha_gestion': 'fecha', 'call_date': 'fecha', 'monto': 'monto_compromiso', 
                'usuario': 'gestor', 'agente': 'gestor', 'user': 'gestor', 'campana': 'campaign', 'campaign_id': 'campaign',
                'glosa': 'glosa', 'comentario': 'glosa', 'comments': 'glosa'
            }
            df.rename(columns=renames, inplace=True)

            if 'rut_cliente' in df.columns:
                df['rut_cliente'] = df['rut_cliente'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df = df[df['rut_cliente'].str.lower() != 'nan']
                df = df[df['rut_cliente'] != '']
            
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=False, errors='coerce')
                df = df.dropna(subset=['fecha'])
                df['fecha'] = df['fecha'].dt.strftime('%Y-%m-%d %H:%M:%S')

            # INSERCIÓN EN POSTGRESQL (NUEVA TABLA: gestiones_raw)
            cols_db = ['fecha', 'gestor', 'rut_cliente', 'telefono', 'cod_gestion', 'monto_compromiso', 'fecha_compromiso', 'campaign', 'glosa']
            cols_a_insertar = [c for c in df.columns if c in cols_db]
            df_final = df[cols_a_insertar]
            
            fecha_ini = f"{target_date} 00:00:00"
            fecha_fin = f"{target_date} 23:59:59"

            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS gestiones_raw (
                        fecha TEXT, gestor TEXT, rut_cliente TEXT, telefono TEXT, 
                        cod_gestion TEXT, monto_compromiso TEXT, fecha_compromiso TEXT, 
                        campaign TEXT, glosa TEXT
                    )
                """))
                conn.execute(text("DELETE FROM gestiones_raw WHERE fecha >= :ini AND fecha <= :fin"), {"ini": fecha_ini, "fin": fecha_fin})
                df_final.to_sql("gestiones_raw", conn, if_exists="append", index=False)

            total_rows_processed += len(df_final)
            log_print(f"Día {target_date} guardado en RAW BD ({len(df_final):,} filas).")

        duration = round(time.time() - start_time_exec, 2)
        msg_final = f"Recolector finalizado. {total_rows_processed} filas procesadas en {duration}s."
        log_print(msg_final)
        return True, msg_final

    except Exception as e:
        error_msg = f"Fallo crítico en Recolector: {str(e)}"
        log_print(error_msg, "error")
        logging.error(traceback.format_exc())
        return False, error_msg

    finally:
        if driver:
            driver.quit()

# =================================================================
# TAREA B: EL INYECTOR SEMANAL (Motor SQL y FTP)
# =================================================================
def tarea_inyector_semanal(cliente):
    log_print(f"Iniciando TAREA DE INYECCIÓN SQL para cliente: {cliente.upper()}")
    try:
        # 1. Obtener la consulta SQL y config SFTP desde la Base de Datos
        with engine.connect() as conn:
            res = conn.execute(text("SELECT columnas FROM layout_configs WHERE cliente = :cli"), {"cli": cliente}).fetchone()
            if not res or not res[0]:
                log_print(f"⚠️ No hay configuración SQL para {cliente}.", "error")
                return False

            config_json = res[0] if isinstance(res[0], dict) else json.loads(res[0])
            consulta_sql = config_json.get('consulta_sql', '')
            prefijo = config_json.get('prefijo_campana', '')
            sftp_config = config_json.get('sftp', {})

        if not consulta_sql:
            log_print(f"⚠️ Consulta SQL vacía para {cliente}. Abortando.", "error")
            return False

        # Si el usuario definió un prefijo, lo aplicamos envolviendo su SQL
        if prefijo:
            # Reemplazamos gestiones_raw temporalmente en la query si aplica
            sql_final = f"SELECT * FROM ({consulta_sql}) AS subquery WHERE campaign LIKE '{prefijo}%'"
            # Si el usuario no seleccionó campaign en su layout, usamos la query original y advertimos
            if "campaign" not in consulta_sql.lower():
                sql_final = consulta_sql
                log_print("Nota: El layout SQL no incluye la columna 'campaign', no se pudo filtrar por prefijo en la capa final.")
        else:
            sql_final = consulta_sql

        log_print("⚙️ Ejecutando Motor SQL de transformación...")
        
        # 2. Ejecutar SQL crudo y cargar directo a Pandas (Magia pura)
        df_sql = pd.read_sql(sql_final, engine)
        
        if df_sql.empty:
            log_print(f"⚠️ El Motor SQL no arrojó resultados para {cliente}. No se enviará FTP.")
            return True

        # 3. Exportar a CSV
        fecha_str = datetime.now().strftime("%d%m%Y")
        archivo_csv_ftp = os.path.join(DOWNLOAD_DIR, f"{cliente.upper()}_GESTIONES_{fecha_str}.csv")
        df_sql.to_csv(archivo_csv_ftp, index=False, sep=',')
        
        # 4. Inyectar al FTP usando el código resiliente
        mes_anio = datetime.now().strftime("%m_%Y")
        ruta_ftp_destino = sftp_config.get('ruta', f'in/gestiones/{mes_anio}')
        
        log_print(f"🌐 Inyectando archivo procesado de {cliente.upper()} al FTP en {ruta_ftp_destino}...")
        exito_inyeccion = inyectar_ftp_resiliente(cliente, archivo_csv_ftp, ruta_ftp_destino)
        
        if exito_inyeccion:
            log_print(f"✅ ¡Inyección FTP exitosa para {cliente} ({len(df_sql)} registros)!")
            return True
        else:
            log_print(f"❌ Falló la inyección FTP para {cliente}.", "error")
            return False

    except Exception as e:
        log_print(f"❌ Error en Inyector SQL Semanal: {str(e)}", "error")
        logging.error(traceback.format_exc())
        return False

# =================================================================
# EJECUCIÓN MANUAL DESDE VUE (Dispara ambas tareas en cadena)
# =================================================================
def ejecutar_extraccion_hites():
    """Función para el Botón Azul del Panel. Corre el día actual y lo inyecta."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    log_print("--- INICIANDO EJECUCIÓN MANUAL A DEMANDA ---")
    
    # 1. Recolectar datos de hoy
    exito_rec, msg_rec = tarea_recolector_nocturno(start_date=hoy, end_date=hoy)
    
    if not exito_rec:
        return False, f"Error en recolección: {msg_rec}"
        
    # 2. Forzar inyección inmediata de Hites (por ser el botón de prueba)
    exito_iny = tarea_inyector_semanal("hites")
    
    if exito_iny:
        return True, f"¡Operación ETL completada! {msg_rec} Archivo Hites inyectado exitosamente."
    else:
        return False, f"Recolección OK, pero falló la inyección FTP. Revisa los logs."