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

def ejecutar_extraccion_hites(start_date=None, end_date=None):
    if not start_date or not end_date:
        hoy = datetime.now().strftime("%Y-%m-%d")
        start_date = hoy
        end_date = hoy

    start_time_exec = time.time()
    total_rows_processed = 0
    driver = None
    date_list = get_date_list(start_date, end_date)

    # =================================================================
    # 2. CARGAR CREDENCIALES DE VICIDIAL DESDE LA BASE DE DATOS
    # =================================================================
    vici_url, vici_user, vici_pass = "", "", ""
    try:
        with engine.connect() as conn:
            res_vici = conn.execute(text("SELECT url, username, password FROM vicidial_configs LIMIT 1")).fetchone()
            if res_vici:
                vici_url, vici_user, vici_pass = res_vici[0], res_vici[1], res_vici[2]
    except Exception as e:
        log_print(f"Error cargando credenciales de Vicidial: {e}", "error")

    if not vici_url or not vici_user or not vici_pass:
        return False, "❌ Faltan credenciales de Vicidial. Por favor, configúralas en la tarjeta del Dashboard."

    # =================================================================
    # SEPARACIÓN DEL FLUJO: URL de Login vs URL de Descarga
    # =================================================================
    login_url = vici_url
    if "index.php" in login_url:
        export_base_url = login_url.replace("index.php", "grilla/export_gestiones.php")
    else:
        export_base_url = "https://vicieffectiva.telexpress.cl/sistema_gestion/grilla/export_gestiones.php"

    # =================================================================
    # 3. CARGAR CONFIGURACIÓN DE LAYOUT HITES DESDE LA BASE DE DATOS
    # =================================================================
    hites_campos = []
    hites_sftp = {}
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT columnas FROM layout_configs WHERE cliente = 'hites'")).fetchone()
            if res and res[0]:
                config_json = res[0] if isinstance(res[0], dict) else json.loads(res[0])
                hites_campos = config_json.get('campos', [])
                hites_sftp = config_json.get('sftp', {})
    except Exception as e:
        log_print(f"Advertencia: No se pudo cargar layout de Hites desde PostgreSQL: {e}", "error")

    if not hites_campos:
        log_print("⚠️ ALERTA: No hay columnas configuradas para Hites en el Dashboard.", "error")

    log_print(f"Iniciando extracción para {len(date_list)} días ({start_date} al {end_date})...")

    try:
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
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

        # ---------------------------------------------------------
        # PASO 1: LOGIN VICIDIAL
        # ---------------------------------------------------------
        log_print(f"Abriendo página de login: {login_url}")
        try:
            driver.get(login_url)
            time.sleep(2) 
            driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "1_pantalla_login.png"))
            
            user_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
            user_field.clear()
            user_field.send_keys(vici_user)
            driver.find_element(By.NAME, 'password').send_keys(vici_pass)
            
            try:
                driver.find_element(By.XPATH, '//input[@name="Submit2" and @value="Ingresar"]').click()
            except:
                driver.find_element(By.NAME, 'password').submit()
            
            time.sleep(3)
            driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "2_pantalla_post_login.png"))
            log_print("Sesión iniciada correctamente. Fotos de validación creadas en descargas.")

        except TimeoutException:
            screenshot_path = os.path.join(DOWNLOAD_DIR, "error_login_vicidial.png")
            driver.save_screenshot(screenshot_path)
            log_print(f"📸 ¡CRASH! La página no cargó o nos bloqueó. Foto guardada en: {screenshot_path}", "error")
            raise Exception("Timeout al intentar cargar el formulario de Vicidial.")

        # ---------------------------------------------------------
        # PASO 2: NAVEGACIÓN Y BUCLE ITERATIVO DE DESCARGA
        # ---------------------------------------------------------
        for target_date in date_list:
            log_print(f"TRABAJANDO: Día {target_date}")
            
            for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")):
                try: os.remove(f)
                except: pass

            direct_download_url = f"{export_base_url}?desde={target_date}&hasta={target_date}&rut=&valor_buscar=RUT&campana="
            log_print(f"Navegando a exportador: {export_base_url} ...")
            
            driver.get(direct_download_url)
            time.sleep(3) 
            driver.save_screenshot(os.path.join(DOWNLOAD_DIR, f"3_pantalla_descarga_{target_date}.png"))
            
            downloaded_file = None
            for _ in range(45): 
                files = [f for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv")) if not f.endswith('.crdownload')]
                if files:
                    latest_file = max(files, key=os.path.getctime)
                    if os.path.getsize(latest_file) > 0:
                        downloaded_file = latest_file
                        break
                time.sleep(1)
                
            if not downloaded_file:
                log_print(f"No se generó reporte para {target_date}. Revisa '3_pantalla_descarga_{target_date}.png'. Saltando...", "error")
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
            
            # ¡SOLUCIÓN APLICADA!: Agregada la palabra 'user' al diccionario para que Pandas la entienda
            renames = {
                'fono': 'telefono', 'telefono_cliente': 'telefono', 'phone_number': 'telefono',
                'rut': 'rut_cliente', 'gestion': 'cod_gestion', 'codigo': 'cod_gestion', 'status': 'cod_gestion',
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

            # ---------------------------------------------------------
            # INSERCIÓN EN POSTGRESQL 
            # ---------------------------------------------------------
            cols_db = ['fecha', 'gestor', 'rut_cliente', 'telefono', 'cod_gestion', 'monto_compromiso', 'fecha_compromiso', 'campaign', 'glosa']
            cols_a_insertar = [c for c in df.columns if c in cols_db]
            df_final = df[cols_a_insertar]
            
            df_final.to_csv(os.path.join(DOWNLOAD_DIR, "ultimo_procesado.csv"), index=False, encoding='utf-8')

            fecha_ini = f"{target_date} 00:00:00"
            fecha_fin = f"{target_date} 23:59:59"

            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS gestiones (
                        fecha TEXT, gestor TEXT, rut_cliente TEXT, telefono TEXT, 
                        cod_gestion TEXT, monto_compromiso TEXT, fecha_compromiso TEXT, 
                        campaign TEXT, glosa TEXT
                    )
                """))
                conn.execute(text("DELETE FROM gestiones WHERE fecha >= :ini AND fecha <= :fin"), {"ini": fecha_ini, "fin": fecha_fin})
                df_final.to_sql("gestiones", conn, if_exists="append", index=False)

            total_rows_processed += len(df_final)
            log_print(f"Día {target_date} guardado con éxito en Base de Datos ({len(df_final):,} filas).")

            # ---------------------------------------------------------
            # GENERACIÓN DE ARCHIVO MANDANTE Y SUBIDA FTP (HITES)
            # ---------------------------------------------------------
            if hites_campos:
                log_print("🔀 Aislando campaña HITE y aplicando Layout dinámico...")
                
                df_hites = df_final[df_final['campaign'].str.contains('HITE', case=False, na=False)].copy()
                
                if not df_hites.empty:
                    df_ftp = pd.DataFrame()
                    
                    # ¡SOLUCIÓN APLICADA!: Condicionales IF para que nunca vuelva a dar KeyError si falta un dato
                    for col in hites_campos:
                        c_name = col['nombre']
                        if 'RUT' in c_name: df_ftp[c_name] = df_hites['rut_cliente'] if 'rut_cliente' in df_hites.columns else ""
                        elif 'TELEFONO' in c_name: df_ftp[c_name] = df_hites['telefono'] if 'telefono' in df_hites.columns else ""
                        elif 'COMENTARIO' in c_name: df_ftp[c_name] = df_hites['glosa'] if 'glosa' in df_hites.columns else ""
                        elif 'FECHA' in c_name: df_ftp[c_name] = pd.to_datetime(df_hites['fecha']).dt.strftime('%d-%m-%Y') if 'fecha' in df_hites.columns else ""
                        elif 'HORA' in c_name: df_ftp[c_name] = pd.to_datetime(df_hites['fecha']).dt.strftime('%H:%M:%S') if 'fecha' in df_hites.columns else ""
                        elif 'GESTOR' in c_name: df_ftp[c_name] = df_hites['gestor'] if 'gestor' in df_hites.columns else ""
                        elif 'ACCION' in c_name or 'RESULTADO' in c_name: df_ftp[c_name] = df_hites['cod_gestion'] if 'cod_gestion' in df_hites.columns else ""
                        elif 'EMPRESA' in c_name: df_ftp[c_name] = "Effectiva SPA"
                        else: df_ftp[c_name] = "" 
                    
                    df_ftp = df_ftp.fillna('')
                    fecha_str = target_date.replace("-", "")
                    archivo_csv_ftp = os.path.join(DOWNLOAD_DIR, f"HITES_GESTIONES_{fecha_str}.csv")
                    df_ftp.to_csv(archivo_csv_ftp, index=False, sep=',')
                    
                    mes_anio = datetime.now().strftime("%m_%Y")
                    ruta_ftp_destino = hites_sftp.get('ruta', f'in/gestiones/{mes_anio}')
                    ruta_ftp_destino = ruta_ftp_destino.replace('mes_año', mes_anio)
                    
                    log_print(f"🌐 Inyectando archivo de Hites al FTP en {ruta_ftp_destino}...")
                    exito_inyeccion = inyectar_ftp_resiliente("hites", archivo_csv_ftp, ruta_ftp_destino)
                    
                    if exito_inyeccion:
                        log_print(f"✅ ¡Inyección FTP exitosa para Hites ({len(df_ftp)} registros)!")
                    else:
                        log_print(f"❌ Falló la inyección FTP para Hites del día {target_date}.", "error")
                else:
                    log_print(f"⚠️ El archivo del día {target_date} no contenía registros de la campaña HITES.")

        duration = round(time.time() - start_time_exec, 2)
        msg_final = f"Extracción completada. {total_rows_processed} filas procesadas en {duration}s."
        log_print(msg_final)
        return True, msg_final

    except Exception as e:
        error_msg = f"Fallo crítico (Posible caída de internet en el contenedor o cambio en la web): {str(e)}"
        
        if driver:
            try:
                screenshot_path = os.path.join(DOWNLOAD_DIR, "error_general.png")
                driver.save_screenshot(screenshot_path)
                log_print(f"📸 Foto del error guardada en: {screenshot_path}", "error")
            except:
                pass
                
        log_print(error_msg, "error")
        logging.error(traceback.format_exc())
        return False, error_msg

    finally:
        if driver:
            driver.quit()