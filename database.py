import sqlite3


def init_db():
    """Crea o conecta con el archivo local apuestas.db y la tabla de partidos."""
    conn = sqlite3.connect('apuestas.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS partidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liga TEXT NOT NULL,
            equipo_local TEXT NOT NULL,
            equipo_visitante TEXT NOT NULL,
            goles_local INTEGER,
            goles_visitante INTEGER,
            corners_local INTEGER,
            corners_visitante INTEGER
        )
    ''')

    conn.commit()
    conn.close()
    print("¡Base de datos SQLite inicializada correctamente!")


def insertar_partido(liga, local, visitante, g_loc, g_vis, c_loc, c_vis):
    """Inserta el resultado y estadísticas de un partido real en la base de datos."""
    conn = sqlite3.connect('apuestas.db')
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO partidos (liga, equipo_local, equipo_visitante, goles_local, goles_visitante, corners_local, corners_visitante)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (liga, local, visitante, g_loc, g_vis, c_loc, c_vis))

    conn.commit()
    conn.close()
    print(f"Partido guardado: {local} vs {visitante} ({liga})")


def obtener_promedios_equipo(equipo):
    """
    Calcula de forma automática los promedios históricos de goles y córneres
    de un equipo (tanto jugando de local como de visitante) desde la base de datos.
    """
    conn = sqlite3.connect('apuestas.db')
    cursor = conn.cursor()

    # 1. Calcular rendimiento jugando de LOCAL
    cursor.execute('''
        SELECT AVG(goles_local), AVG(corners_local) 
        FROM partidos WHERE equipo_local = ?
    ''', (equipo,))
    res_local = cursor.fetchone()

    # 2. Calcular rendimiento jugando de VISITANTE
    cursor.execute('''
        SELECT AVG(goles_visitante), AVG(corners_visitante) 
        FROM partidos WHERE equipo_visitante = ?
    ''', (equipo,))
    res_visitante = cursor.fetchone()

    conn.close()

    # Si no hay registros suficientes, asignamos valores por defecto seguros
    goles_l = res_local[0] if res_local and res_local[0] is not None else 1.3
    corners_l = res_local[1] if res_local and res_local[1] is not None else 5.0

    goles_v = res_visitante[0] if res_visitante and res_visitante[0] is not None else 1.0
    corners_v = res_visitante[1] if res_visitante and res_visitante[1] is not None else 4.0

    return {
        "goles_favor_local": round(goles_l, 2),
        "corners_favor_local": round(corners_l, 2),
        "goles_favor_visitante": round(goles_v, 2),
        "corners_favor_visitante": round(corners_v, 2)
    }


if __name__ == '__main__':
    # Inicializamos la BD
    init_db()

    # Insertemos un par de partidos de ejemplo (ej. Liga BetPlay)
    insertar_partido("Liga BetPlay", "Millonarios", "Santa Fe", 2, 1, 6, 4)
    insertar_partido("Liga BetPlay", "Millonarios", "Junior", 1, 1, 7, 3)

    # Probemos consultando los promedios históricos de Millonarios como local
    promedios = obtener_promedios_equipo("Millonarios")
    print("\nPromedios calculados para Millonarios:", promedios)