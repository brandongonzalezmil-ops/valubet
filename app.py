from corners_model import calcular_corners_partido
from database import init_db, insertar_partido, obtener_promedios_equipo
from poisson_model import calcular_probabilidades_poisson
from api_client import obtener_partidos_competencia
import streamlit as st
import numpy as np
from scipy.stats import poisson

# Inicializar base de datos local
init_db()

st.set_page_config(
    page_title="ValuBet - Analizador de Apuestas", page_icon="⚽", layout="centered"
)

st.title("⚽ ValuBet - Analizador de Apuestas")
st.write(
    "Herramienta cuantitativa para detectar *Value Bets* en Goles (1X2) y"
    " Córneres (con soporte de API y Base de Datos)."
)

# Menú lateral para navegar
menu = st.sidebar.selectbox(
    "Menú de Navegación", ["Analizar Partido", "Registrar Partido Manual", "Ver Partidos de la API"]
)

# Ligas principales de la API gratuita (con sus códigos oficiales)
LIGAS_API = {
    "Premier League (Inglaterra)": "PL",
    "La Liga (España)": "PD",
    "Serie A (Italia)": "SA",
    "Bundesliga (Alemania)": "BL1",
    "Ligue 1 (Francia)": "FL1",
    "Champions League": "CL"
}

LISTA_LIGAS_MANUAL = [
    "Liga BetPlay (Colombia)",
    "Premier League (Inglaterra)",
    "La Liga (España)",
    "Serie A (Italia)",
    "Bundesliga (Alemania)",
    "Ligue 1 (Francia)",
    "Otra / Personalizada",
]


def evaluar_apuesta_valor(prob_modelo_porcentaje, cuota_casa):
  prob_decimal = prob_modelo_porcentaje / 100.0
  expectativa_valor = prob_decimal * cuota_casa
  prob_implicita_casa = (1 / cuota_casa) * 100
  tiene_valor = expectativa_valor > 1.0
  return {
      "tiene_valor": tiene_valor,
      "expectativa": round(expectativa_valor, 3),
      "prob_implicita": round(prob_implicita_casa, 2),
  }


# --- OPCIÓN 1: REGISTRAR PARTIDO MANUALMENTE ---
if menu == "Registrar Partido Manual":
  st.header("📝 Registrar Nuevo Partido en la BD")

  with st.form("form_registro"):
    liga_seleccionada = st.selectbox("Selecciona la Liga", LISTA_LIGAS_MANUAL)

    if liga_seleccionada == "Otra / Personalizada":
      liga = st.text_input("Escribe el nombre de la Liga")
    else:
      liga = liga_seleccionada

    local = st.text_input("Equipo Local")
    visitante = st.text_input("Equipo Visitante")

    col1, col2 = st.columns(2)
    with col1:
      g_loc = st.number_input("Goles Local", min_value=0, step=1, value=1)
      c_loc = st.number_input("Córneres Local", min_value=0, step=1, value=5)
    with col2:
      g_vis = st.number_input("Goles Visitante", min_value=0, step=1, value=1)
      c_vis = st.number_input("Córneres Visitante", min_value=0, step=1, value=4)

    submit = st.form_submit_button("Guardar en Base de Datos")

    if submit:
      if local and visitante and liga:
        insertar_partido(liga, local, visitante, g_loc, g_vis, c_loc, c_vis)
        st.success(
            f"¡Partido guardado con éxito en {liga}: {local} vs {visitante}!"
        )
      else:
        st.error("Por favor completa los nombres de los equipos.")


# --- OPCIÓN 2: VER PARTIDOS DESDE LA API ---
elif menu == "Ver Partidos de la API":
  st.header("🌐 Partidos en la API (Ligas Europeas)")
  st.write("Consulta los próximos encuentros o partidos de la jornada directamente desde la API.")

  liga_api_elegida = st.selectbox("Selecciona la Competición", list(LIGAS_API.keys()))
  codigo_competencia = LIGAS_API[liga_api_elegida]

  if st.button("Cargar Partidos de la API"):
    partidos = obtener_partidos_competencia(codigo_competencia)
    if partidos:
      st.success(f"Se encontraron {len(partidos)} partidos para {liga_api_elegida}.")
      for p in partidos[:10]: # Mostramos los primeros 10
        home = p['homeTeam']['name']
        away = p['awayTeam']['name']
        utc_date = p['utcDate'].replace("T", " ")[:16]
        status = p['status']
        st.text(f"📅 {utc_date} | ⚽ {home} vs {away} [{status}]")
    else:
      st.warning("No se pudieron cargar partidos o la API no arrojó resultados en este momento.")


# --- OPCIÓN 3: ANALIZAR PARTIDO Y RECOMENDACIONES ---
elif menu == "Analizar Partido":
  st.header("🔍 Análisis y Value Betting")

  liga_seleccionada = st.selectbox(
      "Filtrar / Indicar Liga para el Análisis", LISTA_LIGAS_MANUAL
  )
  if liga_seleccionada == "Otra / Personalizada":
    liga = st.text_input("Escribe el nombre de la Liga", "Internacional")
  else:
    liga = liga_seleccionada

  col_a, col_b = st.columns(2)
  with col_a:
    local = st.text_input("Equipo Local a Analizar", "Real Madrid")
  with col_b:
    visitante = st.text_input("Equipo Visitante a Analizar", "Barcelona")

  st.subheader("💰 Cuotas de la Casa de Apuestas")
  col_c1, col_c2, col_c3 = st.columns(3)
  with col_c1:
    cuota_local = st.number_input(
        "Cuota Gana Local", min_value=1.01, value=2.10, step=0.01
    )
  with col_c2:
    linea_c = st.number_input(
        "Línea Córneres", min_value=0.5, value=9.5, step=0.5
    )
  with col_c3:
    cuota_over_c = st.number_input(
        "Cuota Over Córneres", min_value=1.01, value=1.90, step=0.01
    )

  # Apuesta base para sugerencias de monto
  apuesta_base = st.number_input(
      "Monto de tu Apuesta Base ($)", min_value=500, value=1000, step=500
  )

  if st.button("Ejecutar Análisis Estadístico", type="primary"):
    # Obtener estadísticas desde SQLite
    stats_local = obtener_promedios_equipo(local)
    stats_visita = obtener_promedios_equipo(visitante)

    lam_goles_loc = stats_local["goles_favor_local"]
    lam_goles_vis = stats_visita["goles_favor_visitante"]
    lam_corn_loc = stats_local["corners_favor_local"]
    lam_corn_vis = stats_visita["corners_favor_visitante"]

    st.markdown("---")
    st.subheader(f"📊 Reporte: {local} vs {visitante} ({liga})")

    # Mostrar lambdas calculados
    col_s1, col_s2 = st.columns(2)
    with col_s1:
      st.info(
          f"**{local} (Local)**\n- Goles esp: {lam_goles_loc}\n- Córneres esp:"
          f" {lam_corn_loc}"
      )
    with col_s2:
      st.info(
          f"**{visitante} (Visita)**\n- Goles esp: {lam_goles_vis}\n- Córneres esp:"
          f" {lam_corn_vis}"
      )

    # 1. Modelo de Goles & 1X2
    st.markdown("### ⚽ Modelo de Goles & 1X2")
    res_goles = calcular_probabilidades_poisson(lam_goles_loc, lam_goles_vis)

    col_g1, col_g2, col_g3 = st.columns(3)
    col_g1.metric(f"Gana {local}", f"{res_goles['prob_local_win']}%")
    col_g2.metric("Empate", f"{res_goles['prob_empate']}%")
    col_g3.metric(f"Gana {visitante}", f"{res_goles['prob_visitante_win']}%")

    val = evaluar_apuesta_valor(res_goles["prob_local_win"], cuota_local)
    st.write(
        f"* **Cuota ofrecida (Local):** {cuota_local} (Probabilidad implícita:"
        f" {val['prob_implicita']}%)"
    )

    if val["tiene_valor"]:
      st.success(
          f"🔥 **¡ALERTA DE VALOR!** Apuesta recomendada al Gana Local"
          f" (Expectativa matemática: {val['expectativa']})"
      )
    else:
      st.warning("❌ Sin valor matemático para el triunfo local.")

    # 2. Modelo de Córneres
    st.markdown("### 🚩 Modelo de Tiros de Esquina")
    res_corners = calcular_corners_partido(
        lam_corn_loc, lam_corn_vis, linea_apuesta=linea_c
    )

    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.metric("Media Córneres", f"{res_corners['lambda_esperado']}")
    col_c2.metric(f"Prob. Over {linea_c}", f"{res_corners['prob_over']}%")
    col_c3.metric(f"Prob. Under {linea_c}", f"{res_corners['prob_under']}%")

    val_c = evaluar_apuesta_valor(res_corners["prob_over"], cuota_over_c)
    st.write(
        f"* **Cuota ofrecida (Over {linea_c}):** {cuota_over_c}"
        f" (Probabilidad implícita: {val_c['prob_implicita']}%)"
    )

    if val_c["tiene_valor"]:
      st.success(
          f"🔥 **¡ALERTA DE VALOR!** Apuesta recomendada al Over de Córneres"
          f" (Expectativa matemática: {val_c['expectativa']})"
      )
    else:
      st.warning("❌ Sin valor matemático para córneres.")

    # --- CÁLCULO DE PROBABILIDADES DE GOLES (OVER/UNDER) Y AMBOS MARCAN ---
    p_over_val = res_goles.get("prob_over_25", 52.5)
    p_under_val = res_goles.get("prob_under_25", 47.5)

    p_no_loc = poisson.pmf(0, lam_goles_loc)
    p_no_vis = poisson.pmf(0, lam_goles_vis)
    prob_ambos_marcan_si = (1 - p_no_loc) * (1 - p_no_vis) * 100
    prob_ambos_marcan_no = 100 - prob_ambos_marcan_si

    # --- SECCIÓN DE RECOMENDACIONES CLAVE Y DIRECTAS ---
    st.markdown("---")
    st.subheader("🎯 Sugerencias Directas de Apuesta")
    st.write(
        "Aquí tienes el desglose exacto de lo más viable mercado por mercado:"
    )

    col_rec1, col_rec2 = st.columns(2)

    with col_rec1:
      st.markdown("#### ⚽ Mercado de Goles")
      if p_over_val > 50:
        st.success(
            f"🔥 **Apuesta recomendada: Over 2.5 Goles**\n- Probabilidad:"
            f" **{p_over_val:.1f}%**"
        )
      else:
        st.info(
            f"🛡️ **Apuesta recomendada: Under 2.5 Goles**\n- Probabilidad:"
            f" **{p_under_val:.1f}%**"
        )

      if prob_ambos_marcan_si > 52:
        st.success(
            f"✅ **Ambos Marcan:** **SÍ** (Probabilidad:"
            f" **{prob_ambos_marcan_si:.1f}%**)"
        )
      else:
        st.warning(
            f"❌ **Ambos Marcan:** **NO** (Probabilidad:"
            f" **{prob_ambos_marcan_
