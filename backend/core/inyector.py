import os
import time
from datetime import datetime
import ftplib
import paramiko

# =================================================================
# CREDENCIALES Y CONFIGURACIÓN POR DEFECTO (SFTP HITES)
# =================================================================
FTP_HOST = os.getenv("FTP_HOST", "sftp.servicioshites.cl")
FTP_PORT = int(os.getenv("FTP_PORT", "22"))
FTP_USER = os.getenv("FTP_USER", "efectiva")
FTP_PASS = os.getenv("FTP_PASSWORD", "5aVsb5f%Y@")
PROTOCOL_DEFAULT = os.getenv("FTP_PROTOCOL", "SFTP")  # SFTP o FTP

# =================================================================
# FUNCIONES AUXILIARES DE CREACIÓN DE DIRECTORIOS
# =================================================================

def crear_directorios_sftp(sftp, ruta):
    """
    Navega de forma recursiva por la ruta en el servidor SFTP (Paramiko)
    y crea las carpetas que no existan.
    """
    carpetas = ruta.strip('/').split('/')
    for carpeta in carpetas:
        if not carpeta:
            continue
        try:
            sftp.chdir(carpeta)
        except IOError:
            print(f"📁 [SFTP] Creando nueva carpeta: {carpeta}")
            try:
                sftp.mkdir(carpeta)
                sftp.chdir(carpeta)
            except Exception as e:
                print(f"⚠️ [SFTP] No se pudo crear la carpeta '{carpeta}': {e}")
                raise e

def crear_directorios_ftp_estandar(ftp, ruta):
    """
    Navega de forma recursiva por la ruta en un servidor FTP estándar (ftplib)
    y crea las carpetas que no existan.
    """
    carpetas = ruta.strip('/').split('/')
    for carpeta in carpetas:
        if not carpeta:
            continue
        try:
            ftp.cwd(carpeta)
        except ftplib.error_perm:
            print(f"📁 [FTP] Creando nueva carpeta: {carpeta}")
            try:
                ftp.mkd(carpeta)
                ftp.cwd(carpeta)
            except Exception as e:
                print(f"⚠️ [FTP] No se pudo crear la carpeta '{carpeta}': {e}")
                raise e

# =================================================================
# MOTORES DE SUBIDA INDIVIDUALES
# =================================================================

def _subir_por_sftp(host, port, user, password, ruta_local, ruta_destino):
    """
    Ejecuta la transferencia cifrada por SSH/SFTP mediante Paramiko.
    """
    transport = None
    sftp = None
    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        print("✅ Autenticación SFTP exitosa.")
        
        try:
            sftp.chdir('/')
        except Exception:
            pass

        crear_directorios_sftp(sftp, ruta_destino)
        
        nombre_archivo = os.path.basename(ruta_local)
        print(f"⬆️ Subiendo archivo vía SFTP: {nombre_archivo} -> {ruta_destino}...")
        
        sftp.put(ruta_local, nombre_archivo)
        print("🎉 ¡Inyección SFTP exitosa! Archivo depositado correctamente.")
        return True
    finally:
        if sftp:
            try:
                sftp.close()
            except Exception:
                pass
        if transport:
            try:
                transport.close()
            except Exception:
                pass

def _subir_por_ftp_estandar(host, port, user, password, ruta_local, ruta_destino):
    """
    Ejecuta la transferencia por FTP tradicional mediante ftplib.
    """
    ftp = None
    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=30)
        ftp.login(user, password)
        ftp.encoding = 'utf-8'
        
        print("✅ Autenticación FTP tradicional exitosa.")
        
        try:
            ftp.cwd('/')
        except Exception:
            pass

        crear_directorios_ftp_estandar(ftp, ruta_destino)
        
        nombre_archivo = os.path.basename(ruta_local)
        print(f"⬆️ Subiendo archivo vía FTP: {nombre_archivo} -> {ruta_destino}...")
        
        with open(ruta_local, 'rb') as archivo:
            ftp.storbinary(f'STOR {nombre_archivo}', archivo)
            
        ftp.quit()
        print("🎉 ¡Inyección FTP exitosa! Archivo depositado correctamente.")
        return True
    finally:
        if ftp:
            try:
                ftp.close()
            except Exception:
                pass

# =================================================================
# ORQUESTADOR Y MOTOR DE RESILIENCIA PRINCIPAL
# =================================================================

def inyectar_ftp_resiliente(cliente, ruta_archivo_local, ruta_ftp_destino, max_reintentos=100, protocolo=None, host=None, port=None, user=None, password=None):
    """
    Función principal invocada por el extractor ETL.
    Admite fallback dinámico entre SFTP y FTP, validación local del archivo,
    traducción de macros de fechas y bucle de reintentos infinitos.
    """
    h_host = host or FTP_HOST
    h_port = port or FTP_PORT
    h_user = user or FTP_USER
    h_pass = password or FTP_PASS
    
    # Determinar el protocolo (si el puerto es 22, fuerza SFTP)
    if protocolo is None:
        if h_port == 22:
            h_proto = "SFTP"
        else:
            h_proto = PROTOCOL_DEFAULT.upper()
    else:
        h_proto = protocolo.upper()

    intento = 1

    # 1. Validar existencia del archivo local en el contenedor
    if not os.path.exists(ruta_archivo_local):
        print(f"❌ Error crítico: El archivo local '{ruta_archivo_local}' no existe.")
        return False

    # 2. Reemplazar plantilla 'mes_año' / 'mes_ano' por fecha dinámicamente
    mes_actual = datetime.now().strftime("%m_%Y")
    ruta_ftp_destino = ruta_ftp_destino.replace('mes_año', mes_actual).replace('mes_ano', mes_actual)

    print(f"🚀 [INYECTOR] Iniciando transferencia para cliente: {cliente.upper()}")
    print(f"📋 Protocolo: {h_proto} | Host: {h_host}:{h_port} | Ruta Destino: {ruta_ftp_destino}")

    # 3. Bucle de reintentos
    while intento <= max_reintentos:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Intento {intento}/{max_reintentos}: Conectando a {h_host}...")
            
            exito = False
            if h_proto == "SFTP":
                exito = _subir_por_sftp(h_host, h_port, h_user, h_pass, ruta_archivo_local, ruta_ftp_destino)
            elif h_proto == "FTP":
                exito = _subir_por_ftp_estandar(h_host, h_port, h_user, h_pass, ruta_archivo_local, ruta_ftp_destino)
            else:
                print(f"❌ Protocolo '{h_proto}' no soportado.")
                return False

            if exito:
                return True

        except Exception as e:
            tiempo_espera = 60
            print(f"❌ Fallo en intento {intento} ({h_proto}): {str(e)}")
            print(f"⏳ El robot esperará {tiempo_espera} segundos antes de reintentar...")
            time.sleep(tiempo_espera)
            intento += 1

    print("🚨 Se agotaron los reintentos máximos configurados.")
    return False