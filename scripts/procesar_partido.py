import sqlite3
import json

ID_EQUIPO_LOCAL = 13071
ID_EQUIPO_VISITANTE = 13072

# =========================================================
# 1. EXTRAER LOS TITULARES
# =========================================================
print("1. Extrayendo quintetos iniciales...")
with open("plantillas_prueba.json", "r", encoding="utf-8") as f:
    datos_maestros = json.load(f)

pista_local = set()
pista_visitante = set()
equipos = datos_maestros.get("teams", [])

if isinstance(equipos, dict):
    equipos = equipos.values()

for equipo in equipos:
    id_del_equipo = equipo.get("teamIdIntern")
    for jugador in equipo.get("players", []):
        if jugador.get("starting") == True:
            actor_id = jugador.get("actorId")
            if id_del_equipo == ID_EQUIPO_LOCAL:
                pista_local.add(actor_id)
            elif id_del_equipo == ID_EQUIPO_VISITANTE:
                pista_visitante.add(actor_id)

print(f"   Local: {pista_local}")
print(f"   Visitante: {pista_visitante}")

# =========================================================
# 2. PREPARAR LA BASE DE DATOS SQLITE
# =========================================================
print("\n2. Preparando Base de Datos...")
conexion = sqlite3.connect("mi_liga.db")
cursor = conexion.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS play_by_play_avanzado (
    eventUuid TEXT PRIMARY KEY,
    period INTEGER,
    min INTEGER,
    sec INTEGER,
    idTeam INTEGER,
    actorId INTEGER,
    idMove INTEGER,
    move TEXT,
    score TEXT,
    quinteto_local TEXT,
    quinteto_visitante TEXT
)
''')
# Limpiamos la tabla para no duplicar datos en nuestras pruebas
cursor.execute('DELETE FROM play_by_play_avanzado')

# =========================================================
# 3. PROCESAR EL PLAY-BY-PLAY Y REGISTRAR ALINEACIONES
# =========================================================
print("\n3. Procesando jugadas y cambios...")
with open("partido_prueba.json", "r", encoding="utf-8") as f:
    jugadas = json.load(f)

jugadas_insertadas = 0

for jugada in jugadas:
    id_movimiento = jugada.get('idMove')
    id_equipo = jugada.get('idTeam')
    actor_id = jugada.get('actorId')

    # A) Actualizar los quintetos si hay cambios
    if id_movimiento == 112: # Entra a pista
        if id_equipo == ID_EQUIPO_LOCAL:
            pista_local.add(actor_id)
        elif id_equipo == ID_EQUIPO_VISITANTE:
            pista_visitante.add(actor_id)
            
    elif id_movimiento == 115: # Sale de pista
        if id_equipo == ID_EQUIPO_LOCAL:
            pista_local.discard(actor_id)
        elif id_equipo == ID_EQUIPO_VISITANTE:
            pista_visitante.discard(actor_id)

    # B) Ordenar los IDs para que la base de datos los reconozca siempre igual
    str_local = str(sorted(list(pista_local)))
    str_visitante = str(sorted(list(pista_visitante)))

    # C) Guardar la jugada en la base de datos
    cursor.execute('''
    INSERT INTO play_by_play_avanzado 
    (eventUuid, period, min, sec, idTeam, actorId, idMove, move, score, quinteto_local, quinteto_visitante)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        jugada.get("eventUuid"),
        jugada.get("period"),
        jugada.get("min"),
        jugada.get("sec"),
        id_equipo,
        actor_id,
        id_movimiento,
        jugada.get("move"),
        jugada.get("score"),
        str_local,
        str_visitante
    ))
    jugadas_insertadas += 1

conexion.commit()
conexion.close()
print(f"\n¡Misión cumplida! Se han guardado {jugadas_insertadas} jugadas en la base de datos.")