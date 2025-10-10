from django import template

register = template.Library()

def _to_number(value):
    try:
        return float(value)
    except Exception:
        return 0.0

@register.filter
def miles(value):
    """
    1234567.89 -> '1.234.568'
    """
    n = int(round(_to_number(value)))
    return f"{n:,}".replace(",", ".")

@register.filter
def money(value):
    """
    1234567.89 -> '$ 1.234.568'
    """
    return f"$ {miles(value)}"
