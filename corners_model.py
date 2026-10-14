from scipy.stats import poisson


def calcular_corners_partido(media_corners_local, media_corners_visitante, linea_apuesta=9.5):
    """
    Calcula la expectativa de tiros de esquina y la probabilidad de Over/Under
    usando la media esperada de ambos equipos.
    """
    # Lambda esperado total de corners en el partido
    lambda_total_corners = media_corners_local + media_corners_visitante

    # Probabilidad acumulada para calcular Over / Under respecto a la línea de apuesta
    # Sumamos las probabilidades desde 0 hasta el valor entero de la línea
    prob_acumulada_bajo = sum([poisson.pmf(i, lambda_total_corners) for i in range(int(linea_apuesta) + 1)])

    prob_over = round((1 - prob_acumulada_bajo) * 100, 2)
    prob_under = round(prob_acumulada_bajo * 100, 2)

    return {
        "lambda_esperado": round(lambda_total_corners, 2),
        "prob_over": prob_over,
        "prob_under": prob_under
    }


# Prueba rápida si ejecutas este archivo solo
if __name__ == '__main__':
    # Ejemplo hipotético: Promedio combinado que apunta a unos 10.5 corners esperados
    res_corners = calcular_corners_partido(5.8, 4.7, linea_apuesta=9.5)
    print("Prueba del Modelo de Tiros de Esquina:")
    print(f"Media esperada de corners: {res_corners['lambda_esperado']}")
    print(f"Probabilidad Over 9.5: {res_corners['prob_over']}%")
    print(f"Probabilidad Under 9.5: {res_corners['prob_under']}%")