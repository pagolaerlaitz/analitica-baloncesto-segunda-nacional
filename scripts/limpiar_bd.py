import sqlite3

def limpiar_jugadores_definitivo():
    conexion = sqlite3.connect("mi_liga.db")
    cursor = conexion.cursor()

    # 1. Eliminar jugadores huérfanos (cuyo equipo fue borrado en el paso anterior)
    cursor.execute("""
        DELETE FROM jugadores 
        WHERE id_equipo NOT IN (SELECT id_equipo FROM equipos)
    """)
    huerfanos_borrados = cursor.rowcount

    # 2. Eliminar cualquier duplicado restante agrupando ÚNICAMENTE por nombre
    cursor.execute("""
        DELETE FROM jugadores 
        WHERE rowid NOT IN (
            SELECT MIN(rowid) 
            FROM jugadores 
            GROUP BY nombre
        )
    """)
    duplicados_borrados = cursor.rowcount

    conexion.commit()
    conexion.close()
    
    print(f"Limpieza de jugadores completada:")
    print(f"- {huerfanos_borrados} jugadores 'huérfanos' eliminados.")
    print(f"- {duplicados_borrados} jugadores duplicados restantes eliminados.")

if __name__ == "__main__":
    limpiar_jugadores_definitivo()