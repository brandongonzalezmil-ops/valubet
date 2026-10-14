import numpy as np
from scipy.stats import poisson


def calcular_probabilidades_poisson(lambda_local, lambda_visitante, max_goles=6):
    """
    Calcula las probabilidades de goles y el mercado 1X2 usando Poisson.
    - lambda_local: Promedio esperado de goles del equipo local.
    - lambda_visitante: Promedio esperado de goles del equipo visitante.
    - max_goles: Tope de goles a evaluar en la matriz (por defecto 6).
    """
    # Probabilidades individuales de anotar i goles para cada equipo
    prob_local = [poisson.pmf(i, lambda_local) for i in range(max_goles + 1)]
    prob_visitante = [poisson.pmf(i, lambda_visitante) for i in range(max_goles + 1)]

    # Matriz de probabilidades combinadas (todos los marcadores exactos)
    matriz_marcador = np.outer(prob_local, prob_visitante)

    prob_local_win = 0.0
    prob_empate = 0.0
    prob_visitante_win = 0.0

    # Sumar las probabilidades según el resultado (1X2)
    for g_loc in range(max_goles + 1):
        for g_vis in range(max_goles + 1):
            p = matriz_marcador[g_loc, g_vis]
            if g_loc > g_vis:
                prob_local_win += p
            elif g_loc == g_vis:
                prob_empate += p
            else:
                prob_visitante_win += p

    return {
        "prob_local_win": round(prob_local_win * 100, 2),
        "prob_empate": round(prob_empate * 100, 2),
        "prob_visitante_win": round(prob_visitante_win * 100, 2)
    }


# Prueba rápida si ejecutas este archivo solo
if __name__ == '__main__':
    # Ejemplo hipotético: Un equipo local con media de 1.8 goles y visita con 1.1
    resultado = calcular_probabilidades_poisson(1.8, 1.1)
    print("Prueba del Modelo de Poisson:")
    print(f"Probabilidad Gana Local: {resultado['prob_local_win']}%")
    print(f"Probabilidad Empate: {resultado['prob_empate']}%")
    print(f"Probabilidad Gana Visitante: {resultado['prob_visitante_win']}%")