import time
from datetime import datetime

def inyectar_sftp_resiliente(cliente, ruta_archivo, ruta_sftp_destino, max_reintentos=100):
    """
    Intenta subir el archivo al SFTP del mandante.
    Si hay una caída de internet o luz, el script se queda "dormido" 
    y vuelve a intentar hasta lograrlo, garantizando la entrega.
    """
    intento = 1
    
    while intento <= max_reintentos:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Intento {intento}: Conectando al SFTP de {cliente.upper()} en ruta {ruta_sftp_destino}...")
            
            # Aquí iría el código real de la librería paramiko para subir al SFTP
            # sftp.put(ruta_archivo, ruta_sftp_destino)
            
            # Simulamos que la conexión falló en el primer intento pero funcionó en el segundo
            if intento == 1:
                raise ConnectionError("No hay internet o el servidor SFTP rechazó la conexión.")
            
            print("✅ ¡Inyección exitosa! Archivo depositado correctamente.")
            return True
            
        except Exception as e:
            tiempo_espera = 60 # Espera 1 minuto antes de volver a martillar
            print(f"❌ Fallo de conexión (Posible corte de luz/internet): {str(e)}")
            print(f"⏳ El robot no se rendirá. Reintentando en {tiempo_espera} segundos...")
            time.sleep(tiempo_espera)
            intento += 1
            
    print("🚨 Se agotaron los reintentos máximos. Revisar servidores.")
    return False