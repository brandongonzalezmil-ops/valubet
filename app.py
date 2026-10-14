import streamlit as st

st.set_page_config(page_title="Analizador de Apuestas de Fútbol", page_icon="⚽", layout="centered")

st.title("⚽ Analizador de Valor - Fútbol")
st.write("Ingresa los datos del partido para evaluar si la apuesta tiene valor matemático positivo (+EV).")

# Sección de entradas del usuario
st.sidebar.header("Parámetros del Partido")
equipo_local = st.sidebar.text_input("Equipo Local", "Local")
equipo_visitante = st.sidebar.text_input("Equipo Visitante", "Visitante")

st.subheader("📊 Datos del Pronóstico y Cuotas")

col_in1, col_in2 = st.columns(2)
with col_in1:
    prob_modelo = st.slider("Probabilidad estimada por tu modelo (%)", 1.0, 100.0, 55.0) / 100.0
with col_in2:
    cuota_casa = st.number_input("Cuota ofrecida por la casa", min_value=1.01, value=2.10, step=0.01)

apuesta_base = st.number_input("Monto de tu Apuesta Base ($)", min_value=500, value=1000, step=500)

# Botón para analizar
if st.button("Analizar Apuesta"):
    # Cálculo del Valor Esperado (EV)
    ev = (prob_modelo * cuota_casa) - 1

    # Determinación de recomendación
    if ev > 0.02:  # Si hay más de 2% de valor positivo
        estado_apuesta = "✅ APUESTA CON VALOR (+EV)"
        sugerencia_seleccion = f"Ganar / Favorable ({equipo_local})"
        monto_recomendado = apuesta_base
    else:
        estado_apuesta = "❌ SIN VALOR / DESCARTAR"
        sugerencia_seleccion = "No Apostar (Margen negativo o neutro)"
        monto_recomendado = 0

    # Visualización clara en Streamlit
    st.markdown("---")
    st.subheader("🎯 Recomendación Final de la Apuesta")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(label="Estado", value=estado_apuesta)

    with col2:
        st.metric(label="Selección Recomendada", value=sugerencia_seleccion)

    with col3:
        st.metric(label="Monto Recomendado", value=f"${monto_recomendado:,.0f}")

    st.info(f"💡 **Valor Esperado (EV) calculado:** {ev * 100:.2f}% (Una cifra mayor a 0% indica valor a largo plazo).")