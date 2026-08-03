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

DB_USER = os.getenv('DB_USER', 'etl_admin')
DB_PASS = os.getenv('DB_PASSWORD', 'etl_password_segura_2026')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'central_etl_db')
POSTGRES_URI = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(POSTGRES_URI)

def log_print(msg, type="info"):
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
# TAREA A: EL RECOLECTOR NOCTURNO (MODO CAMARÓGRAFO BLINDADO)
# =================================================================
def tarea_recolector_nocturno(start_date=None, end_date=None):
    if not start_date or not end_date:
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
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gestiones_raw (
                    fecha TEXT, gestor TEXT, rut_cliente TEXT, telefono TEXT, 
                    cod_gestion TEXT, monto_compromiso TEXT, fecha_compromiso TEXT, 
                    campaign TEXT, glosa TEXT
                )
            """))

        # Limpieza inicial
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")):
            if not "GESTIONES" in f: 
                try: os.remove(f)
                except: pass
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.png")):
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

        log_print(f"Abriendo página de login: {login_url}")
        driver.get(login_url)
        time.sleep(2) 
        
        # 📸 FOTO 1: Antes de loguearse
        driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "1_pantalla_antes_login.png"))
        log_print("📸 [FOTO TOMADA]: 1_pantalla_antes_login.png")

        user_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        user_field.clear()
        user_field.send_keys(vici_user)
        driver.find_element(By.NAME, 'password').send_keys(vici_pass)
        
        try:
            driver.find_element(By.XPATH, '//input[@name="Submit2" and @value="Ingresar"]').click()
        except:
            driver.find_element(By.NAME, 'password').submit()
        
        time.sleep(4) # Esperamos 4 segundos para asegurarnos de que la página cargó
        
        # 📸 FOTO 2: Después de loguearse
        driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "2_pantalla_despues_login.png"))
        log_print("📸 [FOTO TOMADA]: 2_pantalla_despues_login.png")
        
        log_print("Sesión iniciada correctamente.")

        for target_date in date_list:
            log_print(f"Descargando datos crudos: Día {target_date}")
            downloaded_file = None
            max_reintentos = 3
            
            # 🔥 CEREBRO ANTI-CAÍDAS: Bucle de Reintentos
            for intento in range(1, max_reintentos + 1):
                if intento > 1:
                    log_print(f"⚠️ Reintento {intento}/{max_reintentos} para el día {target_date}...")
                    driver.refresh() # Refrescamos para "despertar" la sesión
                    time.sleep(3)

                direct_download_url = f"{export_base_url}?desde={target_date}&hasta={target_date}&rut=&valor_buscar=RUT&campana="
                
                # TRUCO NINJA: Inyectamos JS para no romper la sesión de Vicidial
                driver.execute_script(f"window.location.href = '{direct_download_url}';")
                time.sleep(3) 
                
                # 📸 FOTO 3: Cuando intenta descargar
                driver.save_screenshot(os.path.join(DOWNLOAD_DIR, f"3_pantalla_descarga_{target_date}_intento_{intento}.png"))
                if intento == 1:
                    log_print(f"📸 [FOTO TOMADA]: 3_pantalla_descarga_{target_date}.png")

                log_print(f"🕵️‍♂️ [FORENSE] Buscando CSV (Intento {intento})...")
                
                # Esperamos hasta 60 segundos por intento
                for i in range(60): 
                    archivos_en_carpeta = os.listdir(DOWNLOAD_DIR)
                    
                    # ¡EL FILTRO CORREGIDO! Ahora busca los que empiezan con GESTIONES-
                    archivos_candidatos = [os.path.join(DOWNLOAD_DIR, f) for f in archivos_en_carpeta if f.startswith('GESTIONES-') and f.lower().endswith('.csv')]
                    valid_files = [f for f in archivos_candidatos if not f.lower().endswith('.crdownload')]
                    
                    if valid_files:
                        latest_file = max(valid_files, key=os.path.getctime)
                        peso = os.path.getsize(latest_file)
                        if peso > 0:
                            downloaded_file = latest_file
                            break
                    time.sleep(1)
                
                # Si encontró el archivo, salimos del bucle de reintentos
                if downloaded_file:
                    break
                else:
                    log_print(f"⏳ Tiempo de espera agotado (60s) en el intento {intento}.", "error")

            # Si después de los reintentos sigue sin archivo, tomamos foto y pasamos al siguiente día
            if not downloaded_file:
                url_actual = driver.current_url
                log_print(f"❌ FALLO DEFINITIVO: No se generó reporte para {target_date} después de {max_reintentos} intentos.", "error")
                # 📸 FOTO 4: Foto del error
                driver.save_screenshot(os.path.join(DOWNLOAD_DIR, f"4_pantalla_error_{target_date}.png"))
                log_print(f"📸 [FOTO TOMADA]: 4_pantalla_error_{target_date}.png")
                continue

            try:
                df = pd.read_csv(downloaded_file, sep=None, engine='python', encoding='latin1', dtype=str, on_bad_lines='skip')
            except:
                df = pd.read_csv(downloaded_file, sep=',', encoding='utf-8', dtype=str, on_bad_lines='skip')

            if df is None or df.empty:
                continue

            df.columns = [str(c).lower().strip().replace(" ", "_").replace(".", "") for c in df.columns]
            
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

            cols_db = ['fecha', 'gestor', 'rut_cliente', 'telefono', 'cod_gestion', 'monto_compromiso', 'fecha_compromiso', 'campaign', 'glosa']
            cols_a_insertar = [c for c in df.columns if c in cols_db]
            df_final = df[cols_a_insertar]
            
            fecha_ini = f"{target_date} 00:00:00"
            fecha_fin = f"{target_date} 23:59:59"

            with engine.begin() as conn:
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
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gestiones_raw (
                    fecha TEXT, gestor TEXT, rut_cliente TEXT, telefono TEXT, 
                    cod_gestion TEXT, monto_compromiso TEXT, fecha_compromiso TEXT, 
                    campaign TEXT, glosa TEXT
                )
            """))

        with engine.connect() as conn:
            res = conn.execute(text("SELECT columnas FROM layout_configs WHERE cliente = :cli"), {"cli": cliente}).fetchone()
            if not res or not res[0]:
                log_print(f"⚠️ No hay configuración SQL para {cliente}.", "error")
                return False

            config_json = res[0] if isinstance(res[0], dict) else json.loads(res[0])
            consulta_sql = config_json.get('consulta_sql', '')
            sftp_config = config_json.get('sftp', {})

        if not consulta_sql:
            return False

        log_print("⚙️ Ejecutando Motor SQL de transformación (Código puro del usuario)...")
        
        with engine.connect() as conn:
            df_sql = pd.read_sql(text(consulta_sql), conn)
        
        if df_sql.empty:
            log_print(f"⚠️ El Motor SQL no arrojó resultados para {cliente}. No se enviará FTP.")
            return True

        fecha_str = datetime.now().strftime("%d%m%Y")
        archivo_csv_ftp = os.path.join(DOWNLOAD_DIR, f"{cliente.upper()}_GESTIONES_{fecha_str}.csv")
        df_sql.to_csv(archivo_csv_ftp, index=False, sep=',')
        
        mes_anio = datetime.now().strftime("%m_%Y")
        ruta_ftp_destino = sftp_config.get('ruta', f'in/gestiones/{mes_anio}')
        
        log_print(f"🌐 Inyectando archivo procesado de {cliente.upper()} al FTP en {ruta_ftp_destino}...")
        exito_inyeccion = inyectar_ftp_resiliente(cliente, archivo_csv_ftp, ruta_ftp_destino)
        
        if exito_inyeccion:
            log_print(f"✅ ¡Inyección FTP exitosa para {cliente} ({len(df_sql)} registros)!")
            return True
        else:
            return False

    except Exception as e:
        log_print(f"❌ Error en Inyector SQL Semanal: {str(e)}", "error")
        return False

# =================================================================
# EJECUCIÓN MANUAL DESDE VUE
# =================================================================
def ejecutar_extraccion_hites():
    hoy = datetime.now().strftime("%Y-%m-%d")
    log_print("--- INICIANDO EJECUCIÓN MANUAL A DEMANDA ---")
    
    exito_rec, msg_rec = tarea_recolector_nocturno(start_date=hoy, end_date=hoy)
    
    if not exito_rec:
        return False, f"Error en recolección: {msg_rec}"
        
    exito_iny = tarea_inyector_semanal("hites")
    
    if exito_iny:
        return True, f"¡Operación ETL completada! {msg_rec} Archivo Hites inyectado exitosamente."
    else:
        return False, f"Recolección OK, pero falló la inyección FTP. Revisa los logs."