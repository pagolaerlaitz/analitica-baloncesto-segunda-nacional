import requests
import json

# 1. Pon aquí la URL exacta de donde sacaste el JSON en la pestaña Network
url_del_json = "https://msstats.optimalwayconsulting.com/v1/esf/getJsonWithMatchMoves/6ab80306bcc75a0001ce0952?currentSeason=true"

# 2. Hacemos la petición a la web
print("Conectando con el servidor...")
respuesta = requests.get(url_del_json)

# 3. Comprobamos si la petición ha tenido éxito (el código 200 significa "Todo OK")
if respuesta.status_code == 200:
    
    # Transformamos la respuesta en datos que Python entiende
    datos_partido = respuesta.json()
    
    # Creamos un archivo en tu ordenador y guardamos los datos
    with open("partido_prueba.json", "w", encoding="utf-8") as archivo:
        json.dump(datos_partido, archivo, indent=4, ensure_ascii=False)
        
    print("¡Éxito! El archivo partido_prueba.json se ha guardado en tu carpeta.")
    
else:
    print(f"Hubo un error al conectar. Código de error: {respuesta.status_code}")