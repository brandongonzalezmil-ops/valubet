import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import nbinom, poisson

from api_client import obtener_equipos_liga, obtener_partidos_competencia, obtener_promedios_api
from database import init_db, insertar_partido, obtener_promedios_equipo

init_db()

st.set_page_config(
    page_title="ValuBet - Analizador de Apuestas", page_icon="⚽", layout="centered"
)

st.title("⚽ ValuBet - Analizador de Apuestas")
st.write("Análisis cuantitativo automatizado con selección inteligente de equipos.")

menu = st.sidebar.selectbox(
    "Menú de Navegación",
    ["Analizar Partido", "Ver Partidos API", "Registrar Partido Manual", "Historial de Apuestas"],
)

st.sidebar.markdown("### ⚙️ Parámetros del modelo")
UMBRAL_EV = st.sidebar.slider("EV mínimo para marcar valor", 1.00, 1.30, 1.05, 0.01)
FRACCION_KELLY = st.sidebar.slider("Fracción de Kelly", 0.05, 1.00, 0.25, 0.05)
VENTAJA_LOCAL = st.sidebar.slider("Ventaja de local (solo modo API)", 1.00, 1.30, 1.10, 0.01)
DISPERSION_CORNERS = st.sidebar.slider("Dispersión córneres (1 = Poisson)", 1.05, 2.00, 1.30, 0.05)

LIGAS_API = {
    "La Liga (España)": "PD",
    "Premier League (Inglaterra)": "PL",
    "Serie A (Italia)": "SA",
    "Bundesliga (Alemania)": "BL1",
    "Ligue 1 (Francia)": "FL1",
    "Champions League": "CL",
}

LISTA_LIGAS_MANUAL = ["Liga BetPlay (Colombia)", "Otra / Personalizada"]


# ---------------------------------------------------------------------------
# Caché de llamadas a la API (evita gastar el límite de peticiones)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def equipos_liga(codigo):
    return obtener_equipos_liga(codigo)


@st.cache_data(ttl=3600)
def promedios_api(equipo, codigo):
    return obtener_promedios_api(equipo, codigo)


@st.cache_data(ttl=600)
def partidos_liga(codigo):
    return obtener_partidos_competencia(codigo)


# ---------------------------------------------------------------------------
# Historial de apuestas (SQLite propio, no toca tu database.py)
# ---------------------------------------------------------------------------
DB_HISTORIAL = "historial_apuestas.db"


def _conn():
    con = sqlite3.connect(DB_HISTORIAL)
    con.execute(
        """CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, partido TEXT, mercado TEXT,
            cuota REAL, monto REAL, resultado TEXT DEFAULT 'pendiente')"""
    )
    return con


def guardar_apuesta(partido, mercado, cuota, monto):
    with _conn() as con:
        con.execute(
            "INSERT INTO apuestas (fecha, partido, mercado, cuota, monto) VALUES (?,?,?,?,?)",
            (str(date.today()), partido, mercado, cuota, monto),
        )


def listar_apuestas():
    con = _conn()
    df = pd.read_sql_query("SELECT * FROM apuestas ORDER BY id DESC", con)
    con.close()
    return df


def actualizar_resultado(id_apuesta, resultado):
    with _conn() as con:
        con.execute("UPDATE apuestas SET resultado = ? WHERE id = ?", (resultado, id_apuesta))


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
def combinar(goles_favor, goles_contra_rival):
    """Mezcla ataque propio con defensa del rival. Si no hay dato de defensa, usa solo ataque."""
    if goles_contra_rival is None:
        return goles_favor
    return (goles_favor + goles_contra_rival) / 2


def calcular_goles(lam_l, lam_v, rho=-0.05, max_goles=10):
    """Poisson bivariado con corrección Dixon-Coles para marcadores bajos."""
    g = np.arange(max_goles + 1)
    m = np.outer(poisson.pmf(g, lam_l), poisson.pmf(g, lam_v))
    m[0, 0] *= 1 - lam_l * lam_v * rho
    m[0, 1] *= 1 + lam_l * rho
    m[1, 0] *= 1 + lam_v * rho
    m[1, 1] *= 1 - rho
    m /= m.sum()

    total = np.add.outer(g, g)
    over25 = m[total > 2].sum()
    btts = 1 - m[0, :].sum() - m[:, 0].sum() + m[0, 0]
    return {
        "local": np.tril(m, -1).sum() * 100,
        "empate": np.trace(m) * 100,
        "visitante": np.triu(m, 1).sum() * 100,
        "over25": over25 * 100,
        "under25": (1 - over25) * 100,
        "btts_si": btts * 100,
        "btts_no": (1 - btts) * 100,
    }


def calcular_corners(lam_l, lam_v, linea, dispersion):
    """Binomial negativa: los córneres suelen tener más varianza que Poisson."""
    mu = lam_l + lam_v
    p = 1 / dispersion
    n = mu * p / (1 - p)
    prob_over = nbinom.sf(int(linea), n, p) * 100
    return {"media": mu, "over": prob_over, "under": 100 - prob_over}


# ---------------------------------------------------------------------------
# Value betting
# ---------------------------------------------------------------------------
def prob_justa(cuotas):
    """Probabilidades implícitas normalizadas (sin el margen de la casa), en %."""
    imp = np.array([1 / c for c in cuotas])
    return imp / imp.sum() * 100


def evaluar(prob_pct, cuota, bankroll):
    p = prob_pct / 100
    ev = p * cuota
    kelly = max(0.0, (p * cuota - 1) / (cuota - 1))
    tiene_valor = ev >= UMBRAL_EV
    monto = bankroll * min(kelly * FRACCION_KELLY, 0.05) if tiene_valor else 0.0
    return ev, tiene_valor, monto


# ---------------------------------------------------------------------------
# MENU: ANALIZAR PARTIDO
# ---------------------------------------------------------------------------
if menu == "Analizar Partido":
    st.header("🔍 Análisis y Value Betting")

    origen_datos = st.radio(
        "Fuente de datos:",
        ["Automático desde API (Ligas Europeas)", "Base de Datos Manual (BetPlay / Otras)"],
    )
    modo_api = "API" in origen_datos

    if modo_api:
        liga_nombre = st.selectbox("Selecciona la Liga en la API", list(LIGAS_API.keys()))
        codigo_liga = LIGAS_API[liga_nombre]
        lista_equipos = equipos_liga(codigo_liga) or ["Sin equipos disponibles"]
    else:
        liga_nombre = st.selectbox("Selecciona la Liga", LISTA_LIGAS_MANUAL)
        codigo_liga = None

    col_a, col_b = st.columns(2)
    with col_a:
        if modo_api:
            local = st.selectbox("Equipo Local", lista_equipos, index=0)
        else:
            local = st.text_input("Equipo Local", "Millonarios")
    with col_b:
        if modo_api:
            visitante = st.selectbox(
                "Equipo Visitante", lista_equipos, index=1 if len(lista_equipos) > 1 else 0
            )
        else:
            visitante = st.text_input("Equipo Visitante", "Santa Fe")

    st.subheader("💰 Cuotas de la Casa de Apuestas")
    c1, c2, c3 = st.columns(3)
    cuota_1 = c1.number_input("Gana Local", min_value=1.01, value=2.10, step=0.01)
    cuota_x = c2.number_input("Empate", min_value=1.01, value=3.30, step=0.01)
    cuota_2 = c3.number_input("Gana Visitante", min_value=1.01, value=3.50, step=0.01)

    c4, c5 = st.columns(2)
    cuota_o25 = c4.number_input("Over 2.5 Goles", min_value=1.01, value=1.95, step=0.01)
    cuota_btts = c5.number_input("Ambos Marcan: Sí", min_value=1.01, value=1.85, step=0.01)

    c6, c7, c8 = st.columns(3)
    linea_c = c6.number_input("Línea Córneres", min_value=0.5, value=9.5, step=1.0)
    cuota_over_c = c7.number_input("Over Córneres", min_value=1.01, value=1.90, step=0.01)
    cuota_under_c = c8.number_input("Under Córneres", min_value=1.01, value=1.90, step=0.01)

    bankroll = st.number_input("Bankroll total ($)", min_value=1000, value=100000, step=5000)

    if st.button("Ejecutar Análisis Estadístico", type="primary"):
        if local == visitante:
            st.error("⚠️ El equipo local y visitante no pueden ser el mismo.")
            st.stop()

        # --- Obtención de datos ---
        if modo_api:
            sl = promedios_api(local, codigo_liga)
            sv = promedios_api(visitante, codigo_liga)
            gc_l, gc_v = sl.get("goles_contra"), sv.get("goles_contra")
            lam_goles_loc = combinar(sl["goles_favor"], gc_v) * VENTAJA_LOCAL
            lam_goles_vis = combinar(sv["goles_favor"], gc_l) / VENTAJA_LOCAL
            lam_corn_loc = sl["corners_estimados"]
            lam_corn_vis = sv["corners_estimados"]
            st.success(
                f"🤖 Datos cargados vía API ({sl['partidos_analizados']} partidos de {local} "
                f"y {sv['partidos_analizados']} de {visitante})."
            )
        else:
            sl = obtener_promedios_equipo(local)
            sv = obtener_promedios_equipo(visitante)
            gc_l = sl.get("goles_contra_local")
            gc_v = sv.get("goles_contra_visitante")
            lam_goles_loc = combinar(sl["goles_favor_local"], gc_v)
            lam_goles_vis = combinar(sv["goles_favor_visitante"], gc_l)
            lam_corn_loc = sl["corners_favor_local"]
            lam_corn_vis = sv["corners_favor_visitante"]  # corregido: antes usaba stats_local
            st.info("📂 Datos cargados desde tu Base de Datos local.")

        if gc_l is None or gc_v is None:
            st.caption(
                "⚠️ No hay goles en contra en tus datos: el modelo usa solo ataque. "
                "Agrega 'goles_contra' para que también considere la defensa del rival."
            )

        lam_goles_loc = max(lam_goles_loc, 0.05)
        lam_goles_vis = max(lam_goles_vis, 0.05)

        # --- Modelos ---
        goles = calcular_goles(lam_goles_loc, lam_goles_vis)
        corn = calcular_corners(lam_corn_loc, lam_corn_vis, linea_c, DISPERSION_CORNERS)

        st.markdown("---")
        st.subheader(f"📊 Reporte: {local} vs {visitante}")

        col_s1, col_s2 = st.columns(2)
        col_s1.info(f"**{local}**\n- Goles esp: {lam_goles_loc:.2f}\n- Córneres esp: {lam_corn_loc:.2f}")
        col_s2.info(f"**{visitante}**\n- Goles esp: {lam_goles_vis:.2f}\n- Córneres esp: {lam_corn_vis:.2f}")

        g1, g2, g3 = st.columns(3)
        g1.metric(f"Gana {local}", f"{goles['local']:.1f}%")
        g2.metric("Empate", f"{goles['empate']:.1f}%")
        g3.metric(f"Gana {visitante}", f"{goles['visitante']:.1f}%")

        k1, k2, k3 = st.columns(3)
        k1.metric("Media Córneres", f"{corn['media']:.1f}")
        k2.metric(f"Over {linea_c}", f"{corn['over']:.1f}%")
        k3.metric(f"Under {linea_c}", f"{corn['under']:.1f}%")

        # --- Tabla de valor: todos los mercados contra su cuota ---
        justa_1x2 = prob_justa([cuota_1, cuota_x, cuota_2])
        justa_corn = prob_justa([cuota_over_c, cuota_under_c])

        mercados = [
            (f"Gana {local}", goles["local"], cuota_1, justa_1x2[0]),
            ("Empate", goles["empate"], cuota_x, justa_1x2[1]),
            (f"Gana {visitante}", goles["visitante"], cuota_2, justa_1x2[2]),
            ("Over 2.5 Goles", goles["over25"], cuota_o25, 100 / cuota_o25),
            ("Ambos Marcan: Sí", goles["btts_si"], cuota_btts, 100 / cuota_btts),
            (f"Over {linea_c} Córneres", corn["over"], cuota_over_c, justa_corn[0]),
            (f"Under {linea_c} Córneres", corn["under"], cuota_under_c, justa_corn[1]),
        ]

        filas = []
        for nombre, prob, cuota, justa in mercados:
            ev, valor, monto = evaluar(prob, cuota, bankroll)
            filas.append(
                {
                    "Mercado": nombre,
                    "Prob. modelo %": round(prob, 1),
                    "Cuota": cuota,
                    "Prob. casa % (sin margen)": round(justa, 1),
                    "EV": round(ev, 3),
                    "Valor": "🔥" if valor else "—",
                    "Monto sugerido": round(monto, -2),
                }
            )

        st.markdown("### 🎯 Valor por mercado")
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

        con_valor = [f for f in filas if f["Valor"] == "🔥"]
        if con_valor:
            mejor = max(con_valor, key=lambda f: f["EV"])
            st.success(f"🔥 Mayor valor: **{mejor['Mercado']}** (EV {mejor['EV']}, monto sugerido ${mejor['Monto sugerido']:,.0f})")
        else:
            st.warning(f"❌ Ningún mercado supera el EV mínimo de {UMBRAL_EV}.")

        st.caption(
            "Un EV alto con un modelo simple suele ser error del modelo, no valor real. "
            "Registra tus apuestas en el Historial y valida con resultados antes de subir montos."
        )

# ---------------------------------------------------------------------------
# MENU: VER PARTIDOS API
# ---------------------------------------------------------------------------
elif menu == "Ver Partidos API":
    st.header("🌐 Próximos Partidos (API)")
    liga_api_elegida = st.selectbox("Selecciona la Competición", list(LIGAS_API.keys()))
    codigo = LIGAS_API[liga_api_elegida]

    if st.button("Cargar Partidos"):
        partidos = partidos_liga(codigo)
        if partidos:
            st.success(f"Partidos encontrados: {len(partidos)}")
            for p in partidos[:12]:
                st.text(f"⚽ {p['homeTeam']['name']} vs {p['awayTeam']['name']} | [{p['status']}]")
        else:
            st.warning("No se encontraron partidos (revisa tu API key o el límite de peticiones).")

# ---------------------------------------------------------------------------
# MENU: REGISTRAR MANUAL
# ---------------------------------------------------------------------------
elif menu == "Registrar Partido Manual":
    st.header("📝 Registrar Partido en BD Local")
    with st.form("form_registro"):
        liga = st.selectbox("Liga", LISTA_LIGAS_MANUAL)
        local = st.text_input("Equipo Local")
        visitante = st.text_input("Equipo Visitante")
        g_loc = st.number_input("Goles Local", min_value=0, value=1)
        c_loc = st.number_input("Córneres Local", min_value=0, value=5)
        g_vis = st.number_input("Goles Visitante", min_value=0, value=1)
        c_vis = st.number_input("Córneres Visitante", min_value=0, value=4)

        if st.form_submit_button("Guardar"):
            if not local.strip() or not visitante.strip():
                st.error("Escribe ambos equipos.")
            else:
                insertar_partido(liga, local.strip(), visitante.strip(), g_loc, g_vis, c_loc, c_vis)
                st.success("Guardado en tu base de datos manual.")

# ---------------------------------------------------------------------------
# MENU: HISTORIAL DE APUESTAS
# ---------------------------------------------------------------------------
elif menu == "Historial de Apuestas":
    st.header("📒 Historial de Apuestas")

    with st.form("form_apuesta"):
        partido = st.text_input("Partido (ej. Millonarios vs Santa Fe)")
        mercado = st.text_input("Mercado (ej. Over 2.5 Goles)")
        cuota = st.number_input("Cuota", min_value=1.01, value=2.00, step=0.01)
        monto = st.number_input("Monto ($)", min_value=0, value=1000, step=500)
        if st.form_submit_button("Guardar apuesta"):
            guardar_apuesta(partido, mercado, cuota, monto)
            st.success("Apuesta guardada.")

    df = listar_apuestas()
    if df.empty:
        st.info("Aún no hay apuestas registradas.")
    else:
        st.dataframe(df, hide_index=True, use_container_width=True)

        col_id, col_res = st.columns(2)
        id_sel = col_id.number_input("ID de la apuesta", min_value=1, step=1)
        res_sel = col_res.selectbox("Resultado", ["pendiente", "ganada", "perdida"])
        if st.button("Actualizar resultado"):
            actualizar_resultado(int(id_sel), res_sel)
            st.rerun()

        resueltas = df[df["resultado"] != "pendiente"]
        if not resueltas.empty:
            ganancia = np.where(
                resueltas["resultado"] == "ganada",
                resueltas["monto"] * (resueltas["cuota"] - 1),
                -resueltas["monto"],
            ).sum()
            roi = ganancia / resueltas["monto"].sum() * 100
            m1, m2, m3 = st.columns(3)
            m1.metric("Apuestas resueltas", len(resueltas))
            m2.metric("Ganancia neta", f"${ganancia:,.0f}")
            m3.metric("ROI", f"{roi:.1f}%")
