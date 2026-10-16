
import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import nbinom, poisson

from api_client import (
    obtener_equipos_liga,
    obtener_ligas_disponibles,
    obtener_partidos_competencia,
    obtener_promedios_api,
)
from database import (
    init_db,
    insertar_partido,
    obtener_equipos_registrados,
    obtener_promedios_equipo,
)

st.set_page_config(
    page_title="ValuBet - Analizador de Apuestas",
    page_icon="⚽",
    layout="centered",
)

init_db()

st.title("⚽ ValuBet - Analizador de Apuestas")
st.write(
    "Análisis cuantitativo automatizado con selección inteligente de equipos."
)

# ---------------------------------------------------------
# MENÚ Y PARÁMETROS
# ---------------------------------------------------------

menu = st.sidebar.selectbox(
    "Menú de Navegación",
    [
        "Analizar Partido",
        "Ver Partidos API",
        "Registrar Partido Manual",
        "Historial de Apuestas",
    ],
)

st.sidebar.markdown("### ⚙️ Parámetros del modelo")

UMBRAL_EV = st.sidebar.slider(
    "EV mínimo para marcar valor", 1.00, 1.30, 1.05, 0.01
)

FRACCION_KELLY = st.sidebar.slider(
    "Fracción de Kelly", 0.05, 1.00, 0.25, 0.05
)

VENTAJA_LOCAL = st.sidebar.slider(
    "Ventaja de local (solo modo API)", 1.00, 1.30, 1.10, 0.01
)

DISPERSION_CORNERS = st.sidebar.slider(
    "Dispersión córneres (1 = Poisson)",
    1.05,
    2.00,
    1.30,
    0.05,
)

LIGAS_BASE = {
    "La Liga (España)": "PD",
    "Premier League (Inglaterra)": "PL",
    "Serie A (Italia)": "SA",
    "Bundesliga (Alemania)": "BL1",
    "Ligue 1 (Francia)": "FL1",
    "Champions League": "CL",
}
LIGAS_API = obtener_ligas_disponibles() or LIGAS_BASE

LISTA_LIGAS_MANUAL = [
    "Liga BetPlay (Colombia)",
    "Otra / Personalizada",
]


# ---------------------------------------------------------
# CONSULTAS A LA API
# ---------------------------------------------------------

def equipos_liga(codigo):
    return obtener_equipos_liga(codigo)


def promedios_api(equipo, codigo):
    return obtener_promedios_api(equipo, codigo)


def partidos_liga(codigo):
    return obtener_partidos_competencia(codigo)


# ---------------------------------------------------------
# HISTORIAL DE APUESTAS
# ---------------------------------------------------------

DB_HISTORIAL = "historial_apuestas.db"


def _conn():
    con = sqlite3.connect(DB_HISTORIAL)

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            partido TEXT,
            mercado TEXT,
            cuota REAL,
            monto REAL,
            resultado TEXT DEFAULT 'pendiente'
        )
        """
    )

    return con


def guardar_apuesta(partido, mercado, cuota, monto):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO apuestas
            (fecha, partido, mercado, cuota, monto)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(date.today()),
                partido,
                mercado,
                cuota,
                monto,
            ),
        )


def listar_apuestas():
    with _conn() as con:
        return pd.read_sql_query(
            "SELECT * FROM apuestas ORDER BY id DESC",
            con,
        )


def actualizar_resultado(id_apuesta, resultado):
    with _conn() as con:
        con.execute(
            "UPDATE apuestas SET resultado = ? WHERE id = ?",
            (resultado, id_apuesta),
        )


# ---------------------------------------------------------
# MODELOS ESTADÍSTICOS
# ---------------------------------------------------------

def combinar(goles_favor, goles_contra_rival):
    if goles_contra_rival is None:
        return float(goles_favor)

    return (float(goles_favor) + float(goles_contra_rival)) / 2


def estimar_corners_sin_datos(goles_favor, base=4.7):
    """
    Estimación provisional de córneres.
    No reemplaza las estadísticas reales de córneres.
    """
    try:
        ataque = float(goles_favor)
    except (TypeError, ValueError):
        ataque = 1.3

    if not np.isfinite(ataque) or ataque <= 0:
        ataque = 1.3

    factor_ataque = ataque / 1.3
    factor_ataque = min(1.10, max(0.85, factor_ataque))

    return base * factor_ataque


def calcular_goles(lam_l, lam_v, rho=-0.05, max_goles=10):
    """Distribución de marcadores con corrección Dixon-Coles."""

    g = np.arange(max_goles + 1)

    m = np.outer(
        poisson.pmf(g, lam_l),
        poisson.pmf(g, lam_v),
    )

    m[0, 0] *= 1 - lam_l * lam_v * rho
    m[0, 1] *= 1 + lam_l * rho
    m[1, 0] *= 1 + lam_v * rho
    m[1, 1] *= 1 - rho

    m /= m.sum()

    total = np.add.outer(g, g)
    over25 = m[total > 2].sum()

    btts = (
        1
        - m[0, :].sum()
        - m[:, 0].sum()
        + m[0, 0]
    )

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
    """
    Calcula probabilidades de Over y Under córneres
    mediante una distribución binomial negativa.
    """
    media = float(lam_l) + float(lam_v)
    linea = float(linea)
    dispersion = float(dispersion)

    if not np.isfinite(media) or media < 0:
        raise ValueError("La media de córneres no es válida.")

    if not np.isfinite(linea):
        raise ValueError("La línea de córneres no es válida.")

    if not np.isfinite(dispersion) or dispersion <= 1:
        dispersion = 1.000001

    if media == 0:
        return {
            "media": 0.0,
            "over": 0.0,
            "under": 100.0,
        }

    p = 1.0 / dispersion
    n = media * p / (1.0 - p)

    # Over 9.5 significa 10 o más córneres.
    # Under 9.5 significa 9 o menos córneres.
    limite = int(np.floor(linea))

    prob_over = float(nbinom.sf(limite, n, p) * 100)
    prob_over = min(100.0, max(0.0, prob_over))

    prob_under = 100.0 - prob_over

    return {
        "media": media,
        "over": prob_over,
        "under": prob_under,
    }


# ---------------------------------------------------------
# VALUE BETTING
# ---------------------------------------------------------

def prob_justa(cuotas):
    """Normaliza las probabilidades implícitas de las cuotas."""
    imp = np.array([1 / c for c in cuotas], dtype=float)
    return imp / imp.sum() * 100


def evaluar(prob_pct, cuota, bankroll):
    p = prob_pct / 100
    ev = p * cuota

    kelly = max(
        0.0,
        (p * cuota - 1) / (cuota - 1),
    )

    tiene_valor = ev >= UMBRAL_EV

    monto = (
        bankroll * min(kelly * FRACCION_KELLY, 0.05)
        if tiene_valor
        else 0.0
    )

    return ev, tiene_valor, monto


# ---------------------------------------------------------
# ANALIZAR PARTIDO
# ---------------------------------------------------------

if menu == "Analizar Partido":

    st.header("🔍 Análisis y Value Betting")

    origen_datos = st.radio(
        "Fuente de datos:",
        [
            "Automático desde API (Ligas Europeas)",
            "Base de Datos Manual (BetPlay / Otras)",
        ],
    )

    modo_api = "API" in origen_datos

    if modo_api:
        liga_nombre = st.selectbox(
            "Selecciona la Liga en la API",
            list(LIGAS_API.keys()),
        )

        codigo_liga = LIGAS_API[liga_nombre]
        lista_equipos = equipos_liga(codigo_liga) or [
            "Sin equipos disponibles"
        ]

    else:
        liga_nombre = st.selectbox(
            "Selecciona la Liga",
            LISTA_LIGAS_MANUAL,
        )

        codigo_liga = None
        lista_equipos = []

    equipos_bd = (
        []
        if modo_api
        else obtener_equipos_registrados()
    )

    col_a, col_b = st.columns(2)

    with col_a:
        if modo_api:
            local = st.selectbox(
                "Equipo Local",
                lista_equipos,
                index=0,
            )
        elif equipos_bd:
            local = st.selectbox(
                "Equipo Local",
                equipos_bd,
                index=0,
            )
        else:
            local = st.text_input("Equipo Local")

    with col_b:
        if modo_api:
            visitante = st.selectbox(
                "Equipo Visitante",
                lista_equipos,
                index=1 if len(lista_equipos) > 1 else 0,
            )
        elif equipos_bd:
            visitante = st.selectbox(
                "Equipo Visitante",
                equipos_bd,
                index=1 if len(equipos_bd) > 1 else 0,
            )
        else:
            visitante = st.text_input("Equipo Visitante")

    st.subheader("💰 Cuotas de la Casa de Apuestas")

    c1, c2, c3 = st.columns(3)

    cuota_1 = c1.number_input(
        "Gana Local",
        min_value=1.01,
        value=2.10,
        step=0.01,
    )

    cuota_x = c2.number_input(
        "Empate",
        min_value=1.01,
        value=3.30,
        step=0.01,
    )

    cuota_2 = c3.number_input(
        "Gana Visitante",
        min_value=1.01,
        value=3.50,
        step=0.01,
    )

    c4, c5 = st.columns(2)

    cuota_o25 = c4.number_input(
        "Over 2.5 Goles",
        min_value=1.01,
        value=1.95,
        step=0.01,
    )

    cuota_btts = c5.number_input(
        "Ambos Marcan: Sí",
        min_value=1.01,
        value=1.85,
        step=0.01,
    )

    c6, c7, c8 = st.columns(3)

    linea_c = c6.number_input(
        "Línea Córneres",
        min_value=0.5,
        value=9.5,
        step=1.0,
    )

    cuota_over_c = c7.number_input(
        "Over Córneres",
        min_value=1.01,
        value=1.90,
        step=0.01,
    )

    cuota_under_c = c8.number_input(
        "Under Córneres",
        min_value=1.01,
        value=1.90,
        step=0.01,
    )

    bankroll = st.number_input(
        "Bankroll total ($)",
        min_value=1000,
        value=100000,
        step=5000,
    )

    if st.button("Ejecutar Análisis Estadístico", type="primary"):

        if not local or not visitante:
            st.error("Debes seleccionar o escribir ambos equipos.")
            st.stop()

        if local == visitante:
            st.error(
                "⚠️ El equipo local y visitante no pueden ser el mismo."
            )
            st.stop()

        if modo_api and lista_equipos == ["Sin equipos disponibles"]:
            st.error("No se pudieron cargar los equipos de la API.")
            st.stop()

        # -------------------------------------------------
        # OBTENER ESTADÍSTICAS
        # -------------------------------------------------

        if modo_api:

            sl = promedios_api(local, codigo_liga)
            sv = promedios_api(visitante, codigo_liga)

            if not sl or not sv:
                st.error(
                    "No se pudieron obtener las estadísticas de ambos "
                    "equipos. Revisa api_client.py y la API key."
                )
                st.stop()

            gf_l = sl.get("goles_favor")
            gf_v = sv.get("goles_favor")
            gc_l = sl.get("goles_contra")
            gc_v = sv.get("goles_contra")

            if gf_l is None or gf_v is None:
                st.error(
                    "La API no devolvió goles a favor suficientes "
                    "para calcular el análisis."
                )
                st.stop()

            lam_goles_loc = combinar(gf_l, gc_v) * VENTAJA_LOCAL
            lam_goles_vis = combinar(gf_v, gc_l) / VENTAJA_LOCAL

            # Estimaciones provisionales de córneres.
            lam_corn_loc = estimar_corners_sin_datos(gf_l)
            lam_corn_vis = estimar_corners_sin_datos(gf_v)

            st.success(
                f"🤖 Datos cargados vía API. "
                f"Partidos analizados: {local}: "
                f"{sl.get('partidos_analizados', 'N/D')}; "
                f"{visitante}: "
                f"{sv.get('partidos_analizados', 'N/D')}."
            )

            st.warning(
                "⚠️ Los córneres del modo API son estimaciones indirectas "
                "basadas en goles, no estadísticas reales de córneres."
            )

        else:

            sl = obtener_promedios_equipo(local)
            sv = obtener_promedios_equipo(visitante)

            if not sl or not sv:
                st.error(
                    "No hay estadísticas suficientes en la base de datos "
                    "para uno de los equipos."
                )
                st.stop()

            gc_l = sl.get("goles_contra_local")
            gc_v = sv.get("goles_contra_visitante")

            lam_goles_loc = combinar(
                sl["goles_favor_local"],
                gc_v,
            )

            lam_goles_vis = combinar(
                sv["goles_favor_visitante"],
                gc_l,
            )

            # En modo manual se usan los córneres registrados.
            lam_corn_loc = sl["corners_favor_local"]
            lam_corn_vis = sv["corners_favor_visitante"]

            st.info("📂 Datos cargados desde tu base de datos manual.")

            n_loc = sl.get("partidos_local", 0)
            n_vis = sv.get("partidos_visitante", 0)

            if n_loc < 5 or n_vis < 5:
                st.warning(
                    f"⚠️ Pocos datos: {local} tiene {n_loc} partidos "
                    f"de local y {visitante} tiene {n_vis} de visitante. "
                    "Los promedios pueden ser poco confiables."
                )

        if gc_l is None or gc_v is None:
            st.caption(
                "⚠️ Faltan datos defensivos de goles. El modelo "
                "usa el ataque disponible cuando sea necesario."
            )

        lam_goles_loc = max(float(lam_goles_loc), 0.05)
        lam_goles_vis = max(float(lam_goles_vis), 0.05)
        lam_corn_loc = max(float(lam_corn_loc), 0.0)
        lam_corn_vis = max(float(lam_corn_vis), 0.0)

        # -------------------------------------------------
        # EJECUTAR MODELOS
        # -------------------------------------------------

        goles = calcular_goles(
            lam_goles_loc,
            lam_goles_vis,
        )

        corn = calcular_corners(
            lam_corn_loc,
            lam_corn_vis,
            linea_c,
            DISPERSION_CORNERS,
        )

        st.markdown("---")
        st.subheader(f"📊 Reporte: {local} vs {visitante}")

        col_s1, col_s2 = st.columns(2)

        col_s1.info(
            f"**{local}**\n\n"
            f"- Goles esperados: {lam_goles_loc:.2f}\n"
            f"- Córneres estimados: {lam_corn_loc:.2f}"
        )

        col_s2.info(
            f"**{visitante}**\n\n"
            f"- Goles esperados: {lam_goles_vis:.2f}\n"
            f"- Córneres estimados: {lam_corn_vis:.2f}"
        )

        g1, g2, g3 = st.columns(3)

        g1.metric(
            f"Gana {local}",
            f"{goles['local']:.1f}%",
        )

        g2.metric(
            "Empate",
            f"{goles['empate']:.1f}%",
        )

        g3.metric(
            f"Gana {visitante}",
            f"{goles['visitante']:.1f}%",
        )

        k1, k2, k3 = st.columns(3)

        k1.metric(
            "Media córneres",
            f"{corn['media']:.1f}",
        )

        k2.metric(
            f"Over {linea_c}",
            f"{corn['over']:.1f}%",
        )

        k3.metric(
            f"Under {linea_c}",
            f"{corn['under']:.1f}%",
        )

        # -------------------------------------------------
        # TABLA DE MERCADOS
        # -------------------------------------------------

        justa_1x2 = prob_justa([
            cuota_1,
            cuota_x,
            cuota_2,
        ])

        # CORRECCIÓN:
        # La columna Prob. casa de córneres muestra los mismos
        # porcentajes del modelo, en lugar del 50/50 de las cuotas.
        justa_corn = [
            corn["over"],
            corn["under"],
        ]

        mercados = [
            (
                f"Gana {local}",
                goles["local"],
                cuota_1,
                justa_1x2[0],
            ),
            (
                "Empate",
                goles["empate"],
                cuota_x,
                justa_1x2[1],
            ),
            (
                f"Gana {visitante}",
                goles["visitante"],
                cuota_2,
                justa_1x2[2],
            ),
            (
                "Over 2.5 Goles",
                goles["over25"],
                cuota_o25,
                100 / cuota_o25,
            ),
            (
                "Ambos Marcan: Sí",
                goles["btts_si"],
                cuota_btts,
                100 / cuota_btts,
            ),
            (
                f"Over {linea_c} Córneres",
                corn["over"],
                cuota_over_c,
                justa_corn[0],
            ),
            (
                f"Under {linea_c} Córneres",
                corn["under"],
                cuota_under_c,
                justa_corn[1],
            ),
        ]

        filas = []

        for nombre, prob, cuota, justa in mercados:

            ev, valor, monto = evaluar(
                prob,
                cuota,
                bankroll,
            )

            es_corner = "Córneres" in nombre

            # CORRECCIÓN:
            # Ya no aparece "Sin validar".
            # En modo API se mantienen desactivadas las
            # recomendaciones de apuestas de córneres.
            if modo_api and es_corner:
                valor_mostrado = "—"
                monto_mostrado = 0
            else:
                valor_mostrado = "🔥" if valor else "—"
                monto_mostrado = round(monto, -2)

            filas.append({
                "Mercado": nombre,
                "Prob. modelo %": round(prob, 1),
                "Cuota": cuota,
                "Prob. casa %": round(justa, 1),
                "EV": round(ev, 3),
                "Valor": valor_mostrado,
                "Monto sugerido": monto_mostrado,
            })

        st.markdown("### 🎯 Valor por mercado")

        st.dataframe(
            pd.DataFrame(filas),
            hide_index=True,
            use_container_width=True,
        )

        con_valor = [
            fila
            for fila in filas
            if fila["Valor"] == "🔥"
        ]

        if con_valor:
            mejor = max(
                con_valor,
                key=lambda fila: fila["EV"],
            )

            st.success(
                f"🔥 Mayor valor estimado: **{mejor['Mercado']}** "
                f"(EV {mejor['EV']:.3f}, monto sugerido "
                f"${mejor['Monto sugerido']:,.0f})."
            )
        else:
            st.warning(
                f"No hay mercados recomendados que superen "
                f"el umbral de EV {UMBRAL_EV:.2f}."
            )

        st.caption(
            "Los resultados son estimaciones, no garantías. "
            "Las probabilidades de córneres en modo API son provisionales "
            "y no constituyen una ventaja estadística validada."
        )


# ---------------------------------------------------------
# VER PARTIDOS API
# ---------------------------------------------------------

elif menu == "Ver Partidos API":

    st.header("🌐 Próximos Partidos (API)")

    liga_api_elegida = st.selectbox(
        "Selecciona la Competición",
        list(LIGAS_API.keys()),
    )

    codigo = LIGAS_API[liga_api_elegida]

    if st.button("Cargar Partidos"):

        partidos = partidos_liga(codigo)

        if partidos:
            st.success(f"Partidos encontrados: {len(partidos)}")

            for partido in partidos[:12]:
                local_api = partido.get(
                    "homeTeam", {}
                ).get("name", "Local desconocido")

                visitante_api = partido.get(
                    "awayTeam", {}
                ).get("name", "Visitante desconocido")

                estado = partido.get(
                    "status", "Estado desconocido"
                )

                st.text(
                    f"⚽ {local_api} vs {visitante_api} | [{estado}]"
                )

        else:
            st.warning(
                "No se encontraron partidos. Revisa la API key, "
                "la competición o el límite de peticiones."
            )


# ---------------------------------------------------------
# REGISTRAR PARTIDO MANUAL
# ---------------------------------------------------------

elif menu == "Registrar Partido Manual":

    st.header("📝 Registrar Partido en BD Local")

    with st.form("form_registro"):

        liga = st.selectbox(
            "Liga",
            LISTA_LIGAS_MANUAL,
        )

        local = st.text_input("Equipo Local")
        visitante = st.text_input("Equipo Visitante")

        g_loc = st.number_input(
            "Goles Local",
            min_value=0,
            value=1,
        )

        c_loc = st.number_input(
            "Córneres Local",
            min_value=0,
            value=5,
        )

        g_vis = st.number_input(
            "Goles Visitante",
            min_value=0,
            value=1,
        )

        c_vis = st.number_input(
            "Córneres Visitante",
            min_value=0,
            value=4,
        )

        enviar_partido = st.form_submit_button("Guardar")

        if enviar_partido:

            if not local.strip() or not visitante.strip():
                st.error("Escribe ambos equipos.")

            elif local.strip() == visitante.strip():
                st.error("Los equipos deben ser diferentes.")

            else:
                insertar_partido(
                    liga,
                    local.strip(),
                    visitante.strip(),
                    g_loc,
                    g_vis,
                    c_loc,
                    c_vis,
                )

                st.success(
                    "Partido guardado en tu base de datos manual."
                )


# ---------------------------------------------------------
# HISTORIAL DE APUESTAS
# ---------------------------------------------------------

elif menu == "Historial de Apuestas":

    st.header("📒 Historial de Apuestas")

    with st.form("form_apuesta"):

        partido = st.text_input(
            "Partido (ej. Millonarios vs Santa Fe)"
        )

        mercado = st.text_input(
            "Mercado (ej. Over 2.5 Goles)"
        )

        cuota = st.number_input(
            "Cuota",
            min_value=1.01,
            value=2.00,
            step=0.01,
        )

        monto = st.number_input(
            "Monto apostado ($)",
            min_value=0,
            value=5000,
            step=1000,
        )

        guardar = st.form_submit_button("Registrar apuesta")

        if guardar:

            if not partido.strip() or not mercado.strip():
                st.error("Escribe el partido y el mercado.")

            elif monto <= 0:
                st.error("El monto debe ser mayor que cero.")

            else:
                guardar_apuesta(
                    partido.strip(),
                    mercado.strip(),
                    cuota,
                    monto,
                )

                st.success("Apuesta registrada correctamente.")

    st.markdown("---")
    st.subheader("📋 Apuestas registradas")

    apuestas = listar_apuestas()

    if apuestas.empty:
        st.info("Todavía no tienes apuestas registradas.")

    else:
        st.dataframe(
            apuestas,
            hide_index=True,
            use_container_width=True,
        )

        st.subheader("Actualizar resultado")

        opciones = {
            f"#{fila['id']} - {fila['partido']} - {fila['mercado']}":
            int(fila["id"])
            for _, fila in apuestas.iterrows()
        }

        seleccion = st.selectbox(
            "Selecciona una apuesta",
            list(opciones.keys()),
        )

        resultado = st.selectbox(
            "Resultado",
            [
                "pendiente",
                "ganada",
                "perdida",
                "anulada",
            ],
        )

        if st.button("Actualizar resultado"):
            actualizar_resultado(
                opciones[seleccion],
                resultado,
            )

            st.success("Resultado actualizado.")
            st.rerun()

