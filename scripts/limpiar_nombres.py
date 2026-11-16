import sqlite3

def quitar_segundo_apellido():
    conexion = sqlite3.connect("mi_liga.db")
    cursor = conexion.cursor()
    
    # Obtenemos todos los jugadores
    cursor.execute("SELECT id_jugador, nombre FROM jugadores")
    jugadores = cursor.fetchall()
    
    actualizados = 0
    for id_jug, nombre in jugadores:
        if nombre:
            partes = nombre.split()
            # Si tiene 3 o más palabras (ej: Mikel Garcia Lopez), quitamos la última
            if len(partes) > 2:
                # Unimos todas las palabras excepto la última
                nuevo_nombre = " ".join(partes[:-1])
                cursor.execute("UPDATE jugadores SET nombre = ? WHERE id_jugador = ?", (nuevo_nombre, id_jug))
                actualizados += 1
                
    conexion.commit()
    conexion.close()
    print(f"¡Limpieza completada! Se han modificado {actualizados} jugadores.")

if __name__ == "__main__":
    quitar_segundo_apellido()