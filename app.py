from datetime import datetime
import sqlite3
import numpy as np
from scipy.stats import poisson
import streamlit as st

# --- CONFIGURACIÓN DE LA BASE DE DATOS SQLITE ---
def init_db():
    conn = sqlite3.connect('apuestas.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            partido TEXT,
            seleccion TEXT,
            cuota REAL,
            monto REAL,
            estado TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Configuración de la página
st.set_page_config(page_title="Analizador y Registro de Apuestas", page_icon="⚽", layout="centered")

st.title("⚽ Analizador de Fútbol + Base de Datos")
st.write(f"¡Hola, Brandon! Aquí tienes tu herramienta completa de análisis y registro manual.")

# --- SECCIÓN 1: PARÁMETROS DEL PARTIDO ---
st.sidebar.header("1. Estadísticas del Partido")
equipo_local = st.sidebar.text_input("Equipo Local", "Local")
equipo_visitante = st.sidebar.text_input("Equipo Visitante", "Visitante")

# Promedios esperados (Goles)
st.sidebar.subheader("Goles esperados (Media)")
lambda_goles_local = st.sidebar.number_input(f"Goles esperados - {equipo_local}", min_value=0.1, value=1.5, step=0.1)
lambda_goles_visit = st.sidebar.number_input(f"Goles esperados - {equipo_visitante}", min_value=0.1, value=1.1, step=0.1)

# Promedios esperados (Córners)
st.sidebar.subheader("Córners esperados (Media)")
lambda_corners_local = st.sidebar.number_input(f"Córners esperados - {equipo_local}", min_value=0.1, value=5.5, step=0.5)
lambda_corners_visit = st.sidebar.number_input(f"Córners esperados - {equipo_visitante}", min_value=0.1, value=4.5, step=0.5)

# --- CÁLCULOS CON POISSON ---
def calcular_probabilidades_goles(l_local, l_visit, max_goles=5):
    matriz = np.outer(poisson.pmf(np.arange(max_goles+1), l_local), poisson.pmf(np.arange(max_goles+1), l_visit))
    prob_local = np.sum(np.tril(matriz, -1))
    prob_empate = np.sum(np.diag(matriz))
    prob_visit = np.sum(np.triu(matriz, 1))
    
    # Over / Under 2.5 Goles
    prob_over_25 = 0
    prob_under_25 = 0
    for i in range(max_goles+1):
        for j in range(max_goles+1):
            if (i + j) > 2.5:
                prob_over_25 += matriz[i, j]
            else:
                prob_under_25 += matriz[i, j]
                
    return prob_local, prob_empate, prob_visit, prob_over_25, prob_under_25

p_local, p_empate, p_visit, p_over, p_under = calcular_probabilidades_goles(lambda_goles_local, lambda_goles_visit)
total_corners_esperados = lambda_corners_local + lambda_corners_visit

# --- MOSTRAR RESULTADOS DEL MODELO ---
st.markdown("---")
st.subheader("📊 Análisis y Viabilidad del Modelo (Poisson)")

col1, col2, col3 = st.columns(3)
col1.metric(f"Victoria {equipo_local}", f"{p_local*100:.1f}%")
col2.metric("Empate", f"{p_empate*100:.1f}%")
col3.metric(f"Victoria {equipo_visitante}", f"{p_visit*100:.1f}%")

st.markdown("---")
col4, col5, col6 = st.columns(3)
col4.metric("Over 2.5 Goles", f"{p_over*100:.1f}%")
col5.metric("Under 2.5 Goles", f"{p_under*100:.1f}%")
col6.metric("Córners Esperados", f"{total_corners_esperados:.1f}")

opciones = {
    f"Victoria {equipo_local}": p_local,
    f"Victoria {equipo_visitante}": p_visit,
    "Over 2.5 Goles": p_over,
    "Under 2.5 Goles": p_under
}
mejor_opcion = max(opciones, key=opciones.get)
st.success(f"🎯 **Opción más viable estadísticamente:** **{mejor_opcion}** ({opciones[mejor_opcion]*100:.1f}%)")


# --- SECCIÓN 2: EVALUADOR DE CUOTAS (+EV) ---
st.markdown("---")
st.subheader("💰 Evaluador de Cuotas de la Casa")

col_cuota1, col_cuota2 = st.columns(2)
with col_cuota1:
    mercado_elegido = st.selectbox(
        "Selecciona el mercado a evaluar:",
        [f"Victoria {equipo_local}", f"Victoria {equipo_visitante}", "Empate", "Over 2.5 Goles", "Under 2.5 Goles"]
    )
    if mercado_elegido == f"Victoria {equipo_local}":
        prob_elegida = p_local
    elif mercado_elegido == f"Victoria {equipo_visitante}":
        prob_elegida = p_visit
    elif mercado_elegido == "Empate":
        prob_elegida = p_empate
    elif mercado_elegido == "Over 2.5 Goles":
        prob_elegida = p_over
    else:
        prob_elegida = p_under

with col_cuota2:
    cuota_casa = st.number_input("Cuota ofrecida", min_value=1.01, value=2.00, step=0.01)

monto_apuesta = st.number_input("Monto a apostar ($)", min_value=500, value=1000, step=500)

if st.button("Evaluar Cuota"):
    ev = (prob_elegida * cuota_casa) - 1
    
    if ev > 0.02:
        estado_eval = "✅ APUESTA CON VALOR (+EV)"
        color_func = st.success
    else:
        estado_eval = "❌ SIN VALOR / DESCARTAR"
        color_func = st.warning

    st.markdown("### Resultado:")
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("Evaluación", estado_eval)
    col_res2.metric("Valor Esperado (EV)", f"{ev*100:.2f}%")
    color_func(f"💡 Probabilidad del modelo: {prob_elegida*100:.1f}% vs Cuota implícita: {(1/cuota_casa)*100:.1f}%")


# --- SECCIÓN 3: REGISTRO MANUAL Y BASE DE DATOS (SQLite) ---
st.markdown("---")
st.subheader("📝 Registrar Apuesta en la Base de Datos")
st.write("Guarda manualmente la apuesta que decidiste realizar para llevar el control en tu historial.")

with st.form("form_registro"):
    nombre_partido = st.text_input("Partido (ej: Millonarios vs Santa Fe)", f"{equipo_local} vs {equipo_visitante}")
    seleccion_manual = st.text_input("Selección apostada", mercado_elegido)
    cuota_manual = st.number_input("Cuota apostada", min_value=1.01, value=cuota_casa, step=0.01)
    monto_manual = st.number_input("Monto apostado ($)", min_value=500, value=monto_apuesta, step=500)
    
    submit_guardar = st.form_submit_button("Guardar en el Historial")
    
    if submit_guardar:
        conn = sqlite3.connect('apuestas.db')
        c = conn.cursor()
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("INSERT INTO historial_apuestas (fecha, partido, seleccion, cuota, monto, estado) VALUES (?, ?, ?, ?, ?, ?)",
                  (fecha_actual, nombre_partido, seleccion_manual, cuota_manual, monto_manual, "Pendiente"))
        conn.commit()
        conn.close()
        st.success("¡Apuesta registrada y guardada en la base de datos con éxito!")

# Mostrar Historial Guardado
st.markdown("---")
st.subheader("📂 Historial de Apuestas Guardadas")
conn = sqlite3.connect('apuestas.db')
cursor = conn.cursor()
cursor.execute("SELECT id, fecha, partido, seleccion, cuota, monto, estado FROM historial_apuestas ORDER BY id DESC")
registros = cursor.fetchall()
conn.close()

if registros:
    for reg in registros:
        st.text(f"ID: {reg[0]} | 📅 {reg[1]} | ⚽ {reg[2]} | 🎯 {reg[3]} | Cuota: {reg[4]} | Monto: ${reg[5]:,.0f} | Estado: {reg[6]}")
else:
    st.info("Aún no tienes apuestas registradas en la base de datos.")
