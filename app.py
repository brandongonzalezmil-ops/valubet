import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import nbinom, poisson

from api_client import (
    obtener_equipos_liga,
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
st.write("Análisis cuantitativo automatizado con selección inteligente de equipos.")

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
    "Fracción de Kelly", 0.05,
