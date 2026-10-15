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

def obtener_equipos_liga(codigo_liga="PD"):
    matches = obtener_partidos_competencia(codigo_liga)
    equipos = set()
    for m in matches:
        if 'homeTeam' in m and 'name' in m['homeTeam']:
            equipos.add(m['homeTeam']['name'])
        if 'awayTeam' in m and 'name' in m['awayTeam']:
            equipos.add(m['awayTeam']['name'])
    return sorted(list(equipos))

def obtener_promedios_api(nombre_equipo, codigo_liga="PD"):
    matches = obtener_partidos_competencia(codigo_liga)
    goles_favor = []
    goles_contra = []
    
    for m in matches:
        if m['status'] == 'FINISHED':
            home = m['homeTeam']['name']
            away = m['awayTeam']['name']
            score_home = m['score']['fullTime']['home']
            score_away = m['score']['fullTime']['home'] if 'home' in m['score']['fullTime'] else 0
            
            # Extraer goles de manera segura
            try:
                sh = m['score']['fullTime']['home']
                sa = m['score']['fullTime']['away']
            except:
                sh, sa = 0, 0
            
            if nombre_equipo.lower() in home.lower():
                if sh is not None and sa is not None:
                    goles_favor.append(sh)
                    goles_contra.append(sa)
            elif nombre_equipo.lower() in away.lower():
                if sh is not None and sa is not None:
                    goles_favor.append(sa)
                    goles_contra.append(sh)
                    
    prom_favor = sum(goles_favor) / len(goles_favor) if goles_favor else 1.2
    prom_contra = sum(goles_contra) / len(goles_contra) if goles_contra else 1.0
    
    # Estimación inteligente y dinámica de córneres basada en los goles a favor y su volumen ofensivo
    # (A mayor promedio de gol e intensidad ofensiva, mayor tendencia a generar saques de esquina)
    base_corners = 4.0 + (prom_favor * 1.1)
    
    return {
        "goles_favor": round(prom_favor, 2),
        "goles_contra": round(prom_contra, 2),
        "corners_estimados": round(base_corners, 1),
        "partidos_analizados": len(goles_favor)
    }
