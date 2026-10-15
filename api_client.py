import requests

API_KEY = "2ba9b7d67707479c8619e75f79ad0971"
BASE_URL = "https://api.football-data.org/v4/"

def obtener_partidos_competencia(codigo_liga="PD"):
    headers = { 'X-Auth-Token': API_KEY }
    url = f"{BASE_URL}competitions/{codigo_liga}/matches"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("matches", [])
    except Exception as e:
        print(f"Error API: {e}")
    return []

def obtener_promedios_api(nombre_equipo, codigo_liga="PD"):
    """
    Busca los partidos jugados recientemente por el equipo en la API 
    y calcula el promedio de goles esperados.
    """
    matches = obtener_partidos_competencia(codigo_liga)
    goles_favor = []
    goles_contra = []
    
    for m in matches:
        if m['status'] == 'FINISHED':
            home = m['homeTeam']['name']
            away = m['awayTeam']['name']
            score_home = m['score']['fullTime']['home']
            score_away = m['score']['fullTime']['away']
            
            if nombre_equipo.lower() in home.lower():
                if score_home is not None and score_away is not None:
                    goles_favor.append(score_home)
                    goles_contra.append(score_away)
            elif nombre_equipo.lower() in away.lower():
                if score_home is not None and score_away is not None:
                    goles_favor.append(score_away)
                    goles_contra.append(score_home)
                    
    prom_favor = sum(goles_favor) / len(goles_favor) if goles_favor else 1.2
    prom_contra = sum(goles_contra) / len(goles_contra) if goles_contra else 1.0
    
    return {
        "goles_favor": round(prom_favor, 2),
        "goles_contra": round(prom_contra, 2),
        "partidos_analizados": len(goles_favor)
    }
