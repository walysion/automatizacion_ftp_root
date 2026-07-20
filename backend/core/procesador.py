import csv
import os
from config.database import LayoutConfig

def procesar_archivo_csv(cliente, ruta_archivo_csv):
    """
    Lee un archivo CSV dinámicamente usando la configuración de columnas
    guardada en PostgreSQL para el cliente especificado.
    """
    print(f"⚙️ Iniciando procesamiento ETL para el cliente: {cliente.upper()}")
    
    # 1. Buscar la estructura obligatoria en la Base de Datos
    layout = LayoutConfig.query.filter_by(cliente=cliente).first()
    if not layout or not layout.columnas:
        return False, f"Error: No existe un layout configurado en la BD para el mandante '{cliente}'."
        
    columnas_requeridas = layout.columnas
    print(f"📋 Layout detectado en BD. El archivo debe contener {len(columnas_requeridas)} columnas.")
    
    # Verificar que el archivo realmente exista en el disco
    if not os.path.exists(ruta_archivo_csv):
        return False, f"Error: El archivo físico no se encuentra en la ruta: {ruta_archivo_csv}"
        
    registros_limpios = []
    
    try:
        # 2. Abrir y leer el archivo CSV usando el delimitador por comas como exige Hites
        with open(ruta_archivo_csv, mode='r', encoding='utf-8') as archivo:
            # Usamos DictReader para emparejar automáticamente las cabeceras
            lector = csv.DictReader(archivo, delimiter=',')
            
            # Sanitizar las cabeceras del archivo real (limpiar espacios y pasar a mayúsculas)
            cabeceras_archivo = [c.strip().upper().replace(' ', '_') for c in lector.fieldnames] if lector.fieldnames else []
            
            # Validar integridad estructural básica
            for col in columnas_requeridas:
                if col['nombre'] not in cabeceras_archivo:
                    return False, f"Error de Integridad: La columna requerida '{col['nombre']}' no viene en el archivo CSV cargado."
            
            # 3. Procesamiento y Limpieza fila por fila
            archivo.seek(0) # Volvemos al inicio del archivo
            next(lector) # Saltamos la línea de cabeceras originales
            
            fila_numero = 1
            for fila in lector:
                fila_numero += 1
                registro_procesado = {}
                
                # Mapeamos cada columna según el tipo configurado en el panel
                for col in columnas_requeridas:
                    nombre_col = col['nombre']
                    tipo_col = col['tipo']
                    
                    # Buscamos el valor original en la fila (manejando variaciones de mayúsculas/minúsculas)
                    valor_original = None
                    for k, v in fila.items():
                        if k.strip().upper().replace(' ', '_') == nombre_col:
                            valor_original = v.strip() if v else ""
                            break
                    
                    # Aplicamos reglas de conversión e higiene de datos según el tipo
                    if tipo_col == "Numero":
                        # Eliminamos puntos, letras o caracteres extraños que rompan enteros
                        valor_limpio = "".join(filter(str.isdigit, valor_original))
                        registro_procesado[nombre_col] = int(valor_limpio) if valor_limpio else 0
                        
                    elif tipo_col == "Decimal":
                        try:
                            registro_procesado[nombre_col] = float(valor_original.replace(',', '.'))
                        except ValueError:
                            registro_procesado[nombre_col] = 0.0
                            
                    elif tipo_col == "Fecha":
                        # Mantiene la fecha limpia (puedes agregar formateos específicos más adelante)
                        registro_procesado[nombre_col] = valor_original
                        
                    else:  # Caso "Texto"
                        registro_procesado[nombre_col] = valor_original
                
                # Guardamos el registro limpio temporalmente
                registros_limpios.append(registro_procesado)
                
        print(f"✅ Procesamiento exitoso. Se limpiaron e higienizaron {len(registros_limpios)} filas del CSV.")
        
        # AQUÍ EN EL SIGUIENTE PASO: Inyectar 'registros_limpios' a la tabla final de gestiones consolidadas
        return True, registros_limpios

    except Exception as e:
        print(f"❌ Error crítico procesando el archivo CSV: {str(e)}")
        return False, f"Excepción en el motor de lectura: {str(e)}"