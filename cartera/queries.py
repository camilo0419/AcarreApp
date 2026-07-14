from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from servicios.models import Servicio


def _saldo_expr():
    return F("valor") - Coalesce(F("anticipo"), Value(0), output_field=IntegerField())


def _cartera_qs(empresa):
    return Servicio.objects.filter(
        ruta__empresa=empresa,
        estado_pago__in=[Servicio.PENDIENTE, Servicio.ANTICIPO],
    )


def cartera_resumen(empresa):
    qs = _cartera_qs(empresa)
    saldo = _saldo_expr()
    total = qs.aggregate(total=Coalesce(Sum(saldo), 0))["total"] or 0
    por_cliente = (
        qs.values("cliente__id", "cliente__nombre")
        .annotate(total=Coalesce(Sum(saldo), 0))
        .filter(total__gt=0)
        .order_by("-total")
    )
    return total, por_cliente


def cartera_por_cliente(empresa, cliente_id):
    return (
        _cartera_qs(empresa)
        .filter(cliente_id=cliente_id)
        .select_related("ruta", "cliente")
        .order_by("-ruta__fecha_salida", "-id")
    )
