from django import template

register = template.Library()


@register.filter
def en_miles(value):
    """
    Divide el valor numérico entre 1000 y le da formato con separador de miles,
    sin decimales.
    Ej: 1530000 -> "1 530"
    """
    try:
        n = float(value) / 1000
        # formatea sin decimales, con separador de miles
        return "{:,.0f}".format(n).replace(",", ".")
    except Exception:
        return value
