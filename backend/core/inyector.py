import os
import time
from datetime import datetime
import ftplib

# ==========================================
# CREDENCIALES DEL SERVIDOR FTP DE PRUEBAS
# ==========================================
FTP_HOST = "ftp.effectivaspa.cl"
FTP_PORT = 21
FTP_USER = "reportes_root@effectivaspa.cl"
FTP_PASS = "Reportes1650/"

def crear_directorios_ftp(ftp, ruta):
    """
    Navega por la ruta en el FTP y crea las carpetas si no existen.
    Ejemplo: Si la ruta es 'in/gestiones/08_2026', entra a 'in', luego a 'gestiones', etc.
    """
    carpetas = ruta.strip('/').split('/')
    for carpeta in carpetas:
        if not carpeta:
            continue
        try:
            ftp.cwd(carpeta)
        except ftplib.error_perm:
            # Si da error, es porque la carpeta no existe, así que la creamos
            print(f"📁 Creando nueva carpeta en el servidor FTP: {carpeta}")
            try:
                ftp.mkd(carpeta)
                ftp.cwd(carpeta)
            except Exception as e:
                print(f"⚠️ No se pudo crear la carpeta {carpeta}. Error de permisos: {e}")
                raise e

def inyectar_ftp_resiliente(cliente, ruta_archivo_local, ruta_ftp_destino, max_reintentos=100):
    """
    Sube el archivo REAL al FTP del mandante usando ftplib.
    Si hay una caída de internet o luz, el script se queda "dormido" 
    y vuelve a intentar hasta lograrlo, garantizando la entrega.
    """
    intento = 1
    
    # Validar que el archivo físico exista en nuestro contenedor antes de intentar subirlo
    if not os.path.exists(ruta_archivo_local):
        print(f"❌ Error: El archivo {ruta_archivo_local} no existe localmente.")
        return False

    # ¡NUEVA INTELIGENCIA!: Traducción automática de fecha
    # Si la ruta dice "mes_año", el inyector lo traduce automáticamente al mes actual.
    # Así aseguramos que en agosto cree "08_2026", en septiembre "09_2026", etc.
    mes_actual = datetime.now().strftime("%m_%Y")
    ruta_ftp_destino = ruta_ftp_destino.replace('mes_año', mes_actual).replace('mes_ano', mes_actual)

    while intento <= max_reintentos:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Intento {intento}: Conectando al FTP de {cliente.upper()} en {FTP_HOST}...")
            
            # 1. Iniciar conexión FTP real
            ftp = ftplib.FTP()
            ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
            ftp.login(FTP_USER, FTP_PASS)
            
            # Forzamos la codificación a UTF-8 para soportar eñes o tildes en rutas futuras
            ftp.encoding = 'utf-8' 
            print("✅ Autenticación exitosa.")
            
            # 2. Navegar y crear la ruta destino (ej: in/gestiones/08_2026)
            ftp.cwd('/') # Volver a la raíz por seguridad
            crear_directorios_ftp(ftp, ruta_ftp_destino)
            
            # 3. Preparar la subida del archivo
            nombre_archivo = os.path.basename(ruta_archivo_local)
            print(f"⬆️ Subiendo archivo: {nombre_archivo} hacia la ruta {ruta_ftp_destino}...")
            
            # Subir el archivo en modo binario (STOR)
            with open(ruta_archivo_local, 'rb') as archivo:
                ftp.storbinary(f'STOR {nombre_archivo}', archivo)
            
            # Cerrar conexión de forma limpia
            ftp.quit()
            print("🎉 ¡Inyección exitosa! Archivo depositado correctamente en el servidor FTP.")
            return True
            
        except ftplib.all_errors as e:
            # Atrapa cualquier error de red, caída de servidor, timeout o credenciales
            tiempo_espera = 60 # Espera 1 minuto antes de volver a martillar
            print(f"❌ Fallo de conexión o subida (Posible corte de red/luz): {str(e)}")
            print(f"⏳ El robot no se rendirá. Reintentando en {tiempo_espera} segundos...")
            time.sleep(tiempo_espera)
            intento += 1
            
        except Exception as e:
            print(f"🚨 Error crítico inesperado en el sistema operativo: {str(e)}")
            break
            
    print("🚨 Se agotaron los reintentos máximos. Revisar conexión a internet o vigencia de credenciales.")
    return False