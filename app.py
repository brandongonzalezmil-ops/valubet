from corners_model import calcular_corners_partido
from database import init_db, insertar_partido, obtener_promedios_equipo
from poisson_model import calcular_probabilidades_poisson
from api_client import obtener_partidos_competencia, obtener_equipos_liga, obtener_promedios_api
import streamlit as st
import numpy as np
from scipy.stats import poisson

init_db()

st.set_page_config(
    page_title="ValuBet - Analizador de Apuestas", page_icon="⚽", layout="centered"
)

st.title("⚽ ValuBet - Analizador de Apuestas")
st.write("Análisis cuantitativo automatizado con selección inteligente de equipos.")

menu = st.sidebar.selectbox(
    "Menú de Navegación", ["Analizar Partido", "Ver Partidos API", "Registrar Partido Manual"]
)

LIGAS_API = {
    "La Liga (España)": "PD",
    "Premier League (Inglaterra)": "PL",
    "Serie A (Italia)": "SA",
    "Bundesliga (Alemania)": "BL1",
    "Ligue 1 (Francia)": "FL1",
    "Champions League": "CL"
}

LISTA_LIGAS_MANUAL = [
    "Liga BetPlay (Colombia)",
    "Otra / Personalizada"
]

def evaluar_apuesta_valor(prob_modelo_porcentaje, cuota_casa):
    prob_decimal = prob_modelo_porcentaje / 100.0
    expectativa_valor = prob_decimal * cuota_casa
    prob_implicita_casa = (1 / cuota_casa) * 100
    tiene_valor = expectativa_valor > 1.0
    return {
        "tiene_valor": tiene_valor,
        "expectativa": round(expectativa_valor, 3),
        "prob_implicita": round(prob_implicita_casa, 2)
    }

# --- MENU: ANALIZAR PARTIDO ---
if menu == "Analizar Partido":
    st.header("🔍 Análisis y Value Betting")
    
    origen_datos = st.radio("Fuente de datos:", ["Automático desde API (Ligas Europeas)", "Base de Datos Manual (BetPlay / Otras)"])
    
    if "API" in origen_datos:
        liga_nombre = st.selectbox("Selecciona la Liga en la API", list(LIGAS_API.keys()))
        codigo_liga = LIGAS_API[liga_nombre]
        
        # Obtenemos la lista real de equipos de la API para los desplegables
        lista_equipos = obtener_equipos_liga(codigo_liga)
        if not lista_equipos:
            lista_equipos = ["Carga los equipos seleccionando la liga"]
    else:
        liga_nombre = st.selectbox("Selecciona la Liga", LISTA_LIGAS_MANUAL)
        codigo_liga = None
        lista_equipos = ["Escribe o registra equipos en tu BD"]

    col_a, col_b = st.columns(2)
    with col_a:
        if "API" in origen_datos:
            local = st.selectbox("Equipo Local", lista_equipos, index=0 if len(lista_equipos) > 0 else 0)
        else:
            local = st.text_input("Equipo Local", "Millonarios")
    with col_b:
        if "API" in origen_datos:
            # Intentar poner por defecto el segundo equipo si existe para que no sea el mismo
            idx_vis = 1 if len(lista_equipos) > 1 else 0
            visitante = st.selectbox("Equipo Visitante", lista_equipos, index=idx_vis)
        else:
            visitante = st.text_input("Equipo Visitante", "Santa Fe")

    st.subheader("💰 Cuotas de la Casa de Apuestas")
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        cuota_local = st.number_input("Cuota Gana Local", min_value=1.01, value=2.10, step=0.01)
    with col_c2:
        linea_c = st.number_input("Línea Córneres", min_value=0.5, value=9.5, step=0.5)
    with col_c3:
        cuota_over_c = st.number_input("Cuota Over Córneres", min_value=1.01, value=1.90, step=0.01)

    apuesta_base = st.number_input("Monto Apuesta Base ($)", min_value=500, value=1000, step=500)

    if st.button("Ejecutar Análisis Estadístico", type="primary"):
        if local == visitante:
            st.error("⚠️ El equipo local y visitante no pueden ser el mismo.")
        else:
            if "API" in origen_datos:
                stats_loc_api = obtener_promedios_api(local, codigo_liga)
                stats_vis_api = obtener_promedios_api(visitante, codigo_liga)
                
                lam_goles_loc = stats_loc_api["goles_favor"]
                lam_goles_vis = stats_vis_api["goles_favor"]
                lam_corn_loc = 5.5
                lam_corn_vis = 4.5
                
                st.success(f"🤖 Datos cargados vía API ({stats_loc_api['partidos_analizados']} partidos de {local} y {stats_vis_api['partidos_analizados']} de {visitante}).")
            else:
                stats_local = obtener_promedios_equipo(local)
                stats_visita = obtener_promedios_equipo(visitante)
                lam_goles_loc = stats_local["goles_favor_local"]
                lam_goles_vis = stats_visita["goles_favor_visitante"]
                lam_corn_loc = stats_local["corners_favor_local"]
                lam_corn_vis = stats_visita["corners_favor_visitante"]
                st.info("📂 Datos cargados desde tu Base de Datos local.")

            st.markdown("---")
            st.subheader(f"📊 Reporte: {local} vs {visitante}")

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.info(f"**{local}**\n- Goles esp: {lam_goles_loc}\n- Córneres esp: {lam_corn_loc}")
            with col_s2:
                st.info(f"**{visitante}**\n- Goles esp: {lam_goles_vis}\n- Córneres esp: {lam_corn_vis}")

            # Modelo Poisson 1X2
            st.markdown("### ⚽ Modelo de Goles & 1X2")
            res_goles = calcular_probabilidades_poisson(lam_goles_loc, lam_goles_vis)

            col_g1, col_g2, col_g3 = st.columns(3)
            col_g1.metric(f"Gana {local}", f"{res_goles['prob_local_win']}%")
            col_g2.metric("Empate", f"{res_goles['prob_empate']}%")
            col_g3.metric(f"Gana {visitante}", f"{res_goles['prob_visitante_win']}%")

            val = evaluar_apuesta_valor(res_goles["prob_local_win"], cuota_local)
            st.write(f"* **Cuota ofrecida:** {cuota_local} (Probabilidad implícita: {val['prob_implicita']}%)")

            if val["tiene_valor"]:
                st.success(f"🔥 **¡ALERTA DE VALOR!** Apuesta recomendada al Gana Local (EV: {val['expectativa']})")
            else:
                st.warning("❌ Sin valor matemático para el triunfo local.")

            # Modelo Córneres
            st.markdown("### 🚩 Modelo de Tiros de Esquina")
            res_corners = calcular_corners_partido(lam_corn_loc, lam_corn_vis, linea_apuesta=linea_c)

            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("Media Córneres", f"{res_corners['lambda_esperado']}")
            col_c2.metric(f"Prob. Over {linea_c}", f"{res_corners['prob_over']}%")
            col_c3.metric(f"Prob. Under {linea_c}", f"{res_corners['prob_under']}%")

            val_c = evaluar_apuesta_valor(res_corners["prob_over"], cuota_over_c)
            st.write(f"* **Cuota ofrecida (Over {linea_c}):** {cuota_over_c} (Prob. implícita: {val_c['prob_implicita']}%)")

            if val_c["tiene_valor"]:
                st.success(f"🔥 **¡ALERTA DE VALOR!** Apuesta recomendada al Over de Córneres")
            else:
                st.warning("❌ Sin valor matemático para córneres.")

            # Recomendaciones directas
            p_over_val = res_goles.get("prob_over_25", 52.5)
            p_under_val = res_goles.get("prob_under_25", 47.5)
            p_no_loc = poisson.pmf(0, lam_goles_loc)
            p_no_vis = poisson.pmf(0, lam_goles_vis)
            prob_ambos_marcan_si = (1 - p_no_loc) * (1 - p_no_vis) * 100
            prob_ambos_marcan_no = 100 - prob_ambos_marcan_si

            st.markdown("---")
            st.subheader("🎯 Sugerencias Directas de Apuesta")

            col_rec1, col_rec2 = st.columns(2)

            with col_rec1:
                st.markdown("#### ⚽ Mercado de Goles")
                if p_over_val > 50:
                    st.success(f"🔥 **Apuesta recomendada: Over 2.5 Goles** ({p_over_val:.1f}%)")
                else:
                    st.info(f"🛡️ **Apuesta recomendada: Under 2.5 Goles** ({p_under_val:.1f}%)")

                if prob_ambos_marcan_si > 52:
                    st.success(f"✅ **Ambos Marcan:** **SÍ** ({prob_ambos_marcan_si:.1f}%)")
                else:
                    st.warning(f"❌ **Ambos Marcan:** **NO** ({prob_ambos_marcan_no:.1f}%)")

            with col_rec2:
                st.markdown("#### 🚩 Mercado de Córneres")
                prob_over_corn = res_corners["prob_over"]
                prob_under_corn = res_corners["prob_under"]

                if prob_over_corn >= prob_under_corn:
                    st.success(f"🔥 **Apuesta recomendada: Over {linea_c} Córneres** ({prob_over_corn}%)")
                else:
                    st.info(f"🛡️ **Apuesta recomendada: Under {linea_c} Córneres** ({prob_under_corn}%)")

                ganador_probable = f"Gana {local}" if res_goles["prob_local_win"] > res_goles["prob_visitante_win"] else f"Gana {visitante}"
                max_prob_ganador = max(res_goles["prob_local_win"], res_goles["prob_visitante_win"])
                st.markdown(f"🏆 **Ganador más viable:** **{ganador_probable}** ({max_prob_ganador}%)")

# --- MENU: VER PARTIDOS API ---
elif menu == "Ver Partidos API":
    st.header("🌐 Próximos Partidos (API)")
    liga_api_elegida = st.selectbox("Selecciona la Competición", list(LIGAS_API.keys()))
    codigo = LIGAS_API[liga_api_elegida]
    
    if st.button("Cargar Partidos"):
        partidos = obtener_partidos_competencia(codigo)
        if partidos:
            st.success(f"Partidos encontrados: {len(partidos)}")
            for p in partidos[:12]:
                st.text(f"⚽ {p['homeTeam']['name']} vs {p['awayTeam']['name']} | [{p['status']}]")

# --- MENU: REGISTRAR MANUAL ---
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
            insertar_partido(liga, local, visitante, g_loc, g_vis, c_loc, c_vis)
            st.success("Guardado en tu base de datos manual.")
