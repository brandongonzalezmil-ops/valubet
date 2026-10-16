import os
import time

import requests

API_KEY = "2ba9b7d67707479c8619e75f79ad0971"
BASE_URL = "https://api.football-data.org/v4/"

# Caché simple en memoria para no repetir peticiones (el plan gratis limita ~10 por minuto)
_CACHE = {}
_TTL_SEGUNDOS = 600


def obtener_partidos_competencia(codigo_liga="PD"):
    ahora = time.time()
    if codigo_liga in _CACHE and ahora - _CACHE[codigo_liga][0] < _TTL_SEGUNDOS:
        return _CACHE[codigo_liga][1]

    if not API_KEY:
        print("Error API: la API_KEY está vacía en api_client.py")
        return []

    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}competitions/{codigo_liga}/matches"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            matches = response.json().get("matches", [])
            _CACHE[codigo_liga] = (ahora, matches)
            return matches
        print(f"Error API {response.status_code}: {response.text[:200]}")
    except requests.RequestException as e:
        print(f"Error API: {e}")
    return []


def obtener_ligas_disponibles(solo_plan_gratis=True):
    """
    Devuelve {"Nombre (País)": "CODIGO"} con las competiciones que ofrece la API.
    Con solo_plan_gratis=True filtra las del plan gratuito (TIER_ONE); si no logra
    filtrarlas, devuelve todas. Se guarda en caché 24 horas.
    """
    ahora = time.time()
    if "_ligas" in _CACHE and ahora - _CACHE["_ligas"][0] < 86400:
        return _CACHE["_ligas"][1]

    if not API_KEY:
        return {}

    try:
        response = requests.get(
            f"{BASE_URL}competitions", headers={"X-Auth-Token": API_KEY}, timeout=15
        )
        if response.status_code == 200:
            comps = response.json().get("competitions", [])
            if solo_plan_gratis:
                comps = [c for c in comps if c.get("plan") == "TIER_ONE"] or comps
            ligas = {
                f"{c['name']} ({c.get('area', {}).get('name', '')})": c["code"]
                for c in comps
                if c.get("code")
            }
            ligas = dict(sorted(ligas.items()))
            _CACHE["_ligas"] = (ahora, ligas)
            return ligas
        print(f"Error API {response.status_code}: {response.text[:200]}")
    except requests.RequestException as e:
        print(f"Error API: {e}")
    return {}


def obtener_equipos_liga(codigo_liga="PD"):
    equipos = set()
    for m in obtener_partidos_competencia(codigo_liga):
        for lado in ("homeTeam", "awayTeam"):
            nombre = m.get(lado, {}).get("name")
            if nombre:
                equipos.add(nombre)
    return sorted(equipos)


def obtener_promedios_api(nombre_equipo, codigo_liga="PD", ultimos=10, decaimiento=0.9):
    """
    Promedios ponderados de los últimos `ultimos` partidos terminados del equipo.
    Los partidos más recientes pesan más (peso = decaimiento ** antigüedad).
    """
    juegos = []  # (fecha, goles_favor, goles_contra)
    for m in obtener_partidos_competencia(codigo_liga):
        if m.get("status") != "FINISHED":
            continue
        ft = m.get("score", {}).get("fullTime", {})
        sh, sa = ft.get("home"), ft.get("away")
        if sh is None or sa is None:
            continue
        # Coincidencia exacta: el nombre viene de la propia lista de equipos de la API
        if m["homeTeam"]["name"] == nombre_equipo:
            juegos.append((m["utcDate"], sh, sa))
        elif m["awayTeam"]["name"] == nombre_equipo:
            juegos.append((m["utcDate"], sa, sh))

    juegos.sort(key=lambda j: j[0], reverse=True)  # más recientes primero
    juegos = juegos[:ultimos]

    if juegos:
        pesos = [decaimiento**i for i in range(len(juegos))]
        total = sum(pesos)
        prom_favor = sum(w * j[1] for w, j in zip(pesos, juegos)) / total
        prom_contra = sum(w * j[2] for w, j in zip(pesos, juegos)) / total
    else:
        prom_favor, prom_contra = 1.2, 1.0  # valores por defecto si no hay datos

    # OJO: esto es una aproximación, no datos reales de córneres
    # (el plan gratis de football-data.org no incluye estadísticas de córneres).
    base_corners = 4.0 + (prom_favor * 1.1)

    return {
        "goles_favor": round(prom_favor, 2),
        "goles_contra": round(prom_contra, 2),
        "corners_estimados": round(base_corners, 1),
        "partidos_analizados": len(juegos),
    }
