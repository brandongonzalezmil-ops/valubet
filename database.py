import sqlite3

DB_PATH = "apuestas.db"


def init_db():
    """Crea o conecta con el archivo local apuestas.db y la tabla de partidos."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
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
        """
    )
    conn.commit()
    conn.close()


def insertar_partido(liga, local, visitante, g_loc, g_vis, c_loc, c_vis):
    """Inserta el resultado y estadísticas de un partido real en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO partidos (liga, equipo_local, equipo_visitante,
                              goles_local, goles_visitante, corners_local, corners_visitante)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (liga, local, visitante, g_loc, g_vis, c_loc, c_vis),
    )
    conn.commit()
    conn.close()
    print(f"Partido guardado: {local} vs {visitante} ({liga})")


def obtener_equipos_registrados(liga=None):
    """Lista de equipos que ya existen en la BD (para autocompletar en la app)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if liga:
        cursor.execute(
            """
            SELECT equipo_local FROM partidos WHERE liga = ?
            UNION
            SELECT equipo_visitante FROM partidos WHERE liga = ?
            """,
            (liga, liga),
        )
    else:
        cursor.execute(
            "SELECT equipo_local FROM partidos UNION SELECT equipo_visitante FROM partidos"
        )
    equipos = sorted(fila[0] for fila in cursor.fetchall())
    conn.close()
    return equipos


def obtener_promedios_equipo(equipo):
    """
    Promedios históricos de goles y córneres de un equipo, separados por
    jugar de local o de visitante, incluyendo los goles que recibe.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Jugando de LOCAL: a favor = goles_local, en contra = goles_visitante
    cursor.execute(
        """
        SELECT AVG(goles_local), AVG(goles_visitante), AVG(corners_local), COUNT(*)
        FROM partidos WHERE equipo_local = ?
        """,
        (equipo,),
    )
    gf_l, gc_l, cor_l, n_l = cursor.fetchone()

    # Jugando de VISITANTE: a favor = goles_visitante, en contra = goles_local
    cursor.execute(
        """
        SELECT AVG(goles_visitante), AVG(goles_local), AVG(corners_visitante), COUNT(*)
        FROM partidos WHERE equipo_visitante = ?
        """,
        (equipo,),
    )
    gf_v, gc_v, cor_v, n_v = cursor.fetchone()

    conn.close()

    # Valores por defecto si el equipo no tiene registros todavía
    return {
        "goles_favor_local": round(gf_l if gf_l is not None else 1.3, 2),
        "goles_contra_local": round(gc_l if gc_l is not None else 1.0, 2),
        "corners_favor_local": round(cor_l if cor_l is not None else 5.0, 2),
        "goles_favor_visitante": round(gf_v if gf_v is not None else 1.0, 2),
        "goles_contra_visitante": round(gc_v if gc_v is not None else 1.3, 2),
        "corners_favor_visitante": round(cor_v if cor_v is not None else 4.0, 2),
        "partidos_local": n_l,
        "partidos_visitante": n_v,
    }


if __name__ == "__main__":
    init_db()
    insertar_partido("Liga BetPlay", "Millonarios", "Santa Fe", 2, 1, 6, 4)
    insertar_partido("Liga BetPlay", "Millonarios", "Junior", 1, 1, 7, 3)

    print("\nPromedios de Millonarios:", obtener_promedios_equipo("Millonarios"))
    print("Equipos registrados:", obtener_equipos_registrados("Liga BetPlay"))
