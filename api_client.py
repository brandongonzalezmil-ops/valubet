import requests

# Tu token real de la API
API_KEY = "2ba9b7d67707479c8619e75f79ad0971"
BASE_URL = "https://api.football-data.org/v4/"

def obtener_partidos_competencia(codigo_liga="PD"):
    """
    Obtiene los partidos de una competición específica. 
    Ejemplos de códigos: 'PD' (La Liga), 'PL' (Premier League), 'SA' (Serie A), 'BL1' (Bundesliga)
    """
    headers = { 'X-Auth-Token': API_KEY }
    url = f"{BASE_URL}competitions/{codigo_liga}/matches"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("matches", [])
    except Exception as e:
        print(f"Error al conectar con la API: {e}")
    return []
