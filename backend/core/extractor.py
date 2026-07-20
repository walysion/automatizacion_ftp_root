import os
import time
import glob
import logging
import traceback
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

# =================================================================
# 2. CREDENCIALES DE VICIDIAL (¡AJUSTA ESTO!)
# =================================================================
VICI_USER = "admin"
VICI_PASS = "3dd3ctiv42025#.."
VICI_URL = "https://vicieffectiva.telexpress.cl/sistema_gestion/grilla/export_gestiones.php"

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

def ejecutar_extraccion_hites(start_date=None, end_date=None):
    """
    Función principal llamada desde app.py.
    """
    # Si no llegan fechas, extraemos el día de ayer por defecto
    if not start_date or not end_date:
        ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = ayer
        end_date = ayer

    start_time_exec = time.time()
    total_rows_processed = 0
    driver = None
    date_list = get_date_list(start_date, end_date)

    log_print(f"Iniciando extracción para {len(date_list)} días ({start_date} al {end_date})...")

    try:
        # Limpieza inicial
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
            try: os.remove(f)
            except: pass

        # Configuración Chromium Headless
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage") 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        
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

        # ---------------------------------------------------------
        # LOGIN VICIDIAL
        # ---------------------------------------------------------
        log_print("Iniciando sesión en Vicidial...")
        driver.get(VICI_URL)
        
        user_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        user_field.clear()
        user_field.send_keys(VICI_USER)
        driver.find_element(By.NAME, 'password').send_keys(VICI_PASS)
        
        try:
            driver.find_element(By.XPATH, '//input[@name="Submit2" and @value="Ingresar"]').click()
        except:
            driver.find_element(By.NAME, 'password').submit()
        
        time.sleep(3)
        log_print("Sesión iniciada correctamente.")

        # ---------------------------------------------------------
        # BUCLE ITERATIVO DE DESCARGA
        # ---------------------------------------------------------
        for target_date in date_list:
            log_print(f"TRABAJANDO: Día {target_date}")
            
            for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")):
                try: os.remove(f)
                except: pass

            direct_download_url = f"{VICI_URL}?desde={target_date}&hasta={target_date}&rut=&valor_buscar=RUT&campana="
            driver.get(direct_download_url)
            
            downloaded_file = None
            for _ in range(45): # Espera hasta 45 segs
                files = [f for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")) if not f.endswith('.crdownload')]
                if files:
                    latest_file = max(files, key=os.path.getctime)
                    if os.path.getsize(latest_file) > 0:
                        downloaded_file = latest_file
                        break
                time.sleep(1)
                
            if not downloaded_file:
                log_print(f"No se generó reporte para {target_date}. Saltando...", "error")
                continue

            # ---------------------------------------------------------
            # PROCESAMIENTO PANDAS
            # ---------------------------------------------------------
            log_print(f"Archivo descargado. Limpiando con Pandas...")
            try:
                df = pd.read_csv(downloaded_file, sep=None, engine='python', encoding='latin1', dtype=str, on_bad_lines='skip')
            except:
                df = pd.read_csv(downloaded_file, sep=',', encoding='utf-8', dtype=str, on_bad_lines='skip')

            if df is None or df.empty:
                log_print(f"El día {target_date} no tiene datos. Saltando...")
                continue

            df.columns = [str(c).lower().strip().replace(" ", "_").replace(".", "") for c in df.columns]
            
            renames = {
                'fono': 'telefono', 'telefono_cliente': 'telefono',
                'rut': 'rut_cliente', 'gestion': 'cod_gestion', 'codigo': 'cod_gestion',
                'fecha_gestion': 'fecha', 'monto': 'monto_compromiso', 
                'usuario': 'user', 'agente': 'user', 'campana': 'campaign',
                'glosa': 'glosa', 'comentario': 'glosa'
            }
            df.rename(columns=renames, inplace=True)

            # Fix RUT
            if 'rut_cliente' in df.columns:
                df['rut_cliente'] = df['rut_cliente'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df = df[df['rut_cliente'].str.lower() != 'nan']
                df = df[df['rut_cliente'] != '']
            
            # Fix Fechas
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=False, errors='coerce')
                df = df.dropna(subset=['fecha'])
                df['fecha'] = df['fecha'].dt.strftime('%Y-%m-%d %H:%M:%S')

            # ---------------------------------------------------------
            # INSERCIÓN EN POSTGRESQL
            # ---------------------------------------------------------
            cols_db = ['fecha', 'user', 'rut_cliente', 'telefono', 'cod_gestion', 'monto_compromiso', 'fecha_compromiso', 'campaign', 'glosa']
            cols_a_insertar = [c for c in df.columns if c in cols_db]
            df_final = df[cols_a_insertar]
            
            # Guardamos la muestra limpia para la Previsualización
            df_final.to_csv(os.path.join(DOWNLOAD_DIR, "ultimo_procesado.csv"), index=False, encoding='utf-8')

            fecha_ini = f"{target_date} 00:00:00"
            fecha_fin = f"{target_date} 23:59:59"

            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS gestiones (
                        fecha TEXT, user TEXT, rut_cliente TEXT, telefono TEXT, 
                        cod_gestion TEXT, monto_compromiso TEXT, fecha_compromiso TEXT, 
                        campaign TEXT, glosa TEXT
                    )
                """))
                # Idempotencia: Borramos el día antes de insertarlo
                conn.execute(text("DELETE FROM gestiones WHERE fecha >= :ini AND fecha <= :fin"), {"ini": fecha_ini, "fin": fecha_fin})
                df_final.to_sql("gestiones", conn, if_exists="append", index=False)

            total_rows_processed += len(df_final)
            log_print(f"Día {target_date} guardado con éxito ({len(df_final):,} filas).")

        # ---------------------------------------------------------
        # FIN DEL PROCESO
        # ---------------------------------------------------------
        duration = round(time.time() - start_time_exec, 2)
        msg_final = f"Extracción completada. {total_rows_processed} filas procesadas en {duration}s."
        log_print(msg_final)
        return True, msg_final

    except Exception as e:
        error_msg = f"Fallo crítico: {str(e)}"
        log_print(error_msg, "error")
        logging.error(traceback.format_exc())
        return False, error_msg

    finally:
        if driver:
            driver.quit()