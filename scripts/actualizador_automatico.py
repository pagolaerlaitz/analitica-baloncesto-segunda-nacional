import sqlite3
import requests
import json
import os
import subprocess
import sys
import time
from alimentar_bd import cargar_datos_relacionales

# 1. LA NUEVA URL MAESTRA (Con el endpoint correcto y el parámetro al final)
URL_MAESTRO_BASE = "https://msstats.optimalwayconsulting.com/v1/esf/getJsonWithMatchStats/{}?currentSeason=true"

# 2. LA URL DE LAS JUGADAS (Que ya funcionaba bien)
URL_PBP_BASE = "https://msstats.optimalwayconsulting.com/v1/esf/getJsonWithMatchMoves/{}?currentSeason=true"

def obtener_partidos_guardados():
    if not os.path.exists("mi_liga.db"):
        return []
    conexion = sqlite3.connect("mi_liga.db")
    cursor = conexion.cursor()
    # Comparamos con el ID de la URL (el del .txt), no con idMatchIntern
    try:
        cursor.execute("SELECT id_externo FROM partidos WHERE id_externo IS NOT NULL")
        guardados = [fila[0] for fila in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Base de datos antigua sin la columna id_externo: se creará en la próxima carga
        guardados = []
    conexion.close()
    return guardados

def descargar_json(url, nombre_archivo):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        respuesta = requests.get(url, headers=headers, timeout=10)
        if respuesta.status_code == 200:
            # MAGIA PURA: Guardamos los datos TAL CUAL los manda la federación, sin tocar nada
            with open(nombre_archivo, "w", encoding="utf-8") as f:
                json.dump(respuesta.json(), f, indent=4, ensure_ascii=False)
            return True
    except Exception as e:
        print(f"Error descargando {url}: {e}")
    return False

def ejecutar_actualizacion_manual():
    print("Iniciando motor de actualización de 2 rutas...")
    
    if not os.path.exists("partidos_a_procesar.txt"):
        print("Crea el archivo 'partidos_a_procesar.txt'.")
        return
        
    with open("partidos_a_procesar.txt", "r") as f:
        lineas = [linea.strip() for linea in f if linea.strip()]
        
    partidos_en_bd = obtener_partidos_guardados()
    nuevos = 0
    
    for linea in lineas:
        # Separamos el ID de la jornada por la coma
        partes = linea.split(',')
        id_partido = partes[0].strip()
        jornada_asignada = partes[1].strip() if len(partes) > 1 else "Desconocida"
        
        if id_partido not in partidos_en_bd:
            print(f"\nDescargando partido {id_partido} (Jornada {jornada_asignada})...")
            
            url_maestro = URL_MAESTRO_BASE.format(id_partido)
            url_pbp = URL_PBP_BASE.format(id_partido)
            
            exito_maestro = descargar_json(url_maestro, "plantillas_prueba.json")
            exito_pbp = descargar_json(url_pbp, "partido_prueba.json")
            
            if exito_maestro and exito_pbp:
                try:
                    # LE PASAMOS LA JORNADA A LA FUNCIÓN DE LA BASE DE DATOS
                    cargar_datos_relacionales(jornada_asignada, id_partido)
                    nuevos += 1
                    print(f"¡Éxito! Partido guardado en SQLite.")
                except Exception as e:
                    print(f"Error al integrar en SQLite: {e}")
            else:
                print("Fallo al descargar uno de los JSON (Maestro o PlayByPlay).")
                
            time.sleep(2)
        else:
            print(f"El partido {id_partido} ya está en la base de datos.")

    if nuevos:
        actualizar_app_movil()
    else:
        print("\nNo hay partidos nuevos: los datos de la app del móvil no cambian.")

def actualizar_app_movil():
    """Regenera los datos de la app del móvil (app_movil/data) con exportar_movil.py.
    Se ejecuta aparte porque carga los cálculos de la app de Streamlit."""
    print("\nActualizando los datos de la app del móvil...")
    resultado = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exportar_movil.py")])
    if resultado.returncode == 0:
        print("App del móvil actualizada: sube la carpeta app_movil a GitHub para verlo en el móvil.")
    else:
        print("Error al actualizar la app del móvil. Ejecuta 'py scripts/exportar_movil.py' para ver el error.")

if __name__ == "__main__":
    ejecutar_actualizacion_manual()