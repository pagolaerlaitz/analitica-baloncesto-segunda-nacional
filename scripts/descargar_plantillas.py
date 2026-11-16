import requests
import json

# 1. Pon aquí la NUEVA URL exacta donde encontraste el Starting = true
url_plantillas = "https://msstats.optimalwayconsulting.com/v1/esf/getJsonWithMatchStats/6ab80306bcc75a0001ce0952?currentSeason=true"

print("Descargando las plantillas y titulares...")
respuesta = requests.get(url_plantillas)

if respuesta.status_code == 200:
    
    datos_plantillas = respuesta.json()
    
    # Lo guardamos con un nombre diferente para no sobreescribir el play-by-play
    with open("plantillas_prueba.json", "w", encoding="utf-8") as archivo:
        json.dump(datos_plantillas, archivo, indent=4, ensure_ascii=False)
        
    print("¡Éxito! El archivo plantillas_prueba.json ya está en tu ordenador.")
    
else:
    print(f"Error al descargar. Código de estado: {respuesta.status_code}")