import streamlit as st
import numpy as np
from scipy.stats import poisson

# Configuración de la página
st.set_page_config(page_title="Analizador Avanzado de Fútbol - Value Betting", page_icon="⚽", layout="centered")

st.title("⚽ Analizador de Apuestas: Poisson & Córners")
st.write(f"¡Hola, Brandon! Ingresa los datos del partido para calcular probabilidades y evaluar cuotas.")

# --- SECCIÓN 1: PARÁMETROS DEL PARTIDO ---
st.sidebar.header("1. Estadísticas del Partido")
equipo_local = st.sidebar.text_input("Equipo Local", "Local")
equipo_visitante = st.sidebar.text_input("Equipo Visitante", "Visitante")

# Promedios esperados (Goles)
st.sidebar.subheader("Goles esperados (Media)")
lambda_goles_local = st.sidebar.number_input(f"Goles esperados - {equipo_local}", min_value=0.1, value=1.5, step=0.1)
lambda_goles_visit = st.sidebar.number_input(f"Goles esperados - {equipo_visitante}", min_value=0.1, value=1.1,
                                             step=0.1)

# Promedios esperados (Córners)
st.sidebar.subheader("Córners esperados (Media)")
lambda_corners_local = st.sidebar.number_input(f"Córners esperados - {equipo_local}", min_value=0.1, value=5.5,
                                               step=0.5)
lambda_corners_visit = st.sidebar.number_input(f"Córners esperados - {equipo_visitante}", min_value=0.1, value=4.5,
                                               step=0.5)


# --- CÁLCULOS CON POISSON ---
def calcular_probabilidades_goles(l_local, l_visit, max_goles=5):
    matriz = np.outer(poisson.pmf(np.arange(max_goles + 1), l_local), poisson.pmf(np.arange(max_goles + 1), l_visit))
    prob_local = np.sum(np.tril(matriz, -1))
    prob_empate = np.sum(np.diag(matriz))
    prob_visit = np.sum(np.triu(matriz, 1))

    # Over / Under 2.5 Goles
    prob_over_25 = 0
    prob_under_25 = 0
    for i in range(max_goles + 1):
        for j in range(max_goles + 1):
            if (i + j) > 2.5:
                prob_over_25 += matriz[i, j]
            else:
                prob_under_25 += matriz[i, j]

    return prob_local, prob_empate, prob_visit, prob_over_25, prob_under_25


p_local, p_empate, p_visit, p_over, p_under = calcular_probabilidades_goles(lambda_goles_local, lambda_goles_visit)

# Córners (Total esperado)
total_corners_esperados = lambda_corners_local + lambda_corners_visit

# --- MOSTRAR RESULTADOS DEL MODELO ---
st.markdown("---")
st.subheader("📊 Análisis y Viabilidad del Modelo (Poisson)")

col1, col2, col3 = st.columns(3)
col1.metric(f"Victoria {equipo_local}", f"{p_local * 100:.1f}%")
col2.metric("Empate", f"{p_empate * 100:.1f}%")
col3.metric(f"Victoria {equipo_visitante}", f"{p_visit * 100:.1f}%")

st.markdown("---")
col4, col5, col6 = st.columns(3)
col4.metric("Over 2.5 Goles", f"{p_over * 100:.1f}%")
col5.metric("Under 2.5 Goles", f"{p_under * 100:.1f}%")
col6.metric("Córners Esperados (Total)", f"{total_corners_esperados:.1f}")

# Determinar automáticamente la opción más viable
opciones = {
    f"Victoria {equipo_local}": p_local,
    f"Victoria {equipo_visitante}": p_visit,
    "Over 2.5 Goles": p_over,
    "Under 2.5 Goles": p_under
}
mejor_opcion = max(opciones, key=opciones.get)

st.success(
    f"🎯 **Opción más viable estadísticamente:** **{mejor_opcion}** (Probabilidad estimada: {opciones[mejor_opcion] * 100:.1f}%)")

# --- SECCIÓN 2: APARTADO DE EVALUACIÓN DE CUOTAS (VALOR ESPERADO) ---
st.markdown("---")
st.subheader("💰 Evaluador de Cuotas de la Casa")
st.write("Introduce la cuota que te ofrece la casa de apuestas para verificar si tiene valor matemático (+EV).")

col_cuota1, col_cuota2 = st.columns(2)
with col_cuota1:
    prob_usuario_input = st.selectbox(
        "Selecciona el mercado a evaluar:",
        [f"Victoria {equipo_local}", f"Victoria {equipo_visitante}", "Empate", "Over 2.5 Goles", "Under 2.5 Goles"]
    )
    # Asignar la probabilidad correspondiente
    if prob_usuario_input == f"Victoria {equipo_local}":
        prob_elegida = p_local
    elif prob_usuario_input == f"Victoria {equipo_visitante}":
        prob_elegida = p_visit
    elif prob_usuario_input == "Empate":
        prob_elegida = p_empate
    elif prob_usuario_input == "Over 2.5 Goles":
        prob_elegida = p_over
    else:
        prob_elegida = p_under

with col_cuota2:
    cuota_casa = st.number_input("Cuota ofrecida por la casa", min_value=1.01, value=2.00, step=0.01)

apuesta_base = st.number_input("Monto base de tu apuesta ($)", min_value=500, value=1000, step=500)

if st.button("Evaluar Cuota"):
    # Cálculo del Valor Esperado (EV) = (Probabilidad * Cuota) - 1
    ev = (prob_elegida * cuota_casa) - 1

    if ev > 0.02:  # Si hay más de 2% de valor positivo
        estado = "✅ APUESTA CON VALOR (+EV)"
        monto_recomendado = apuesta_base
        color_msg = st.success
    else:
        estado = "❌ SIN VALOR / DESCARTAR"
        monto_recomendado = 0
        color_msg = st.warning

    st.markdown("### Resultado de la Evaluación:")
    col_res1, col_res2 = st.columns(2)
    col_res1.metric(label="Estado de la Cuota", value=estado)
    col_res2.metric(label="Monto Sugerido", value=f"${monto_recomendado:,.0f}")

    color_msg(
        f"💡 **Valor Esperado (EV):** {ev * 100:.2f}% | Probabilidad del modelo: {prob_elegida * 100:.1f}% vs Cuota implícita: {(1 / cuota_casa) * 100:.1f}%")
st.info(f"💡 **Valor Esperado (EV) calculado:** {ev * 100:.2f}% (Una cifra mayor a 0% indica valor a largo plazo).")