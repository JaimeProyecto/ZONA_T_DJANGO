# core/templatetags/miles.py
from django import template

register = template.Library()


@register.filter
def formato_miles(value):
    """
    Formatea un número entero o decimal con separador de miles (puntos),
    sin decimales. Ej: 17000 → "17.000"
    """
    try:
        # convierte a float y redondea cero decimales
        texto = "{:,.0f}".format(float(value))
        # sustituye comas por puntos
        return texto.replace(",", ".")
    except Exception:
        return value
