from collections import defaultdict

from servicios.models import Servicio

from .services import servicios_con_saldo


def _cartera_qs(empresa):
    return servicios_con_saldo(
        Servicio.objects.filter(ruta__empresa=empresa).select_related("ruta", "cliente")
    )


def cartera_resumen(empresa):
    servicios = list(_cartera_qs(empresa))
    total = sum(int(servicio.saldo_cartera or 0) for servicio in servicios)
    por_cliente = defaultdict(lambda: {"total": 0, "cliente__id": None, "cliente__nombre": ""})
    for servicio in servicios:
        row = por_cliente[servicio.cliente_id]
        row["cliente__id"] = servicio.cliente_id
        row["cliente__nombre"] = servicio.cliente.nombre
        row["total"] += int(servicio.saldo_cartera or 0)
    return total, sorted(por_cliente.values(), key=lambda item: item["total"], reverse=True)


def cartera_por_cliente(empresa, cliente_id):
    return (
        _cartera_qs(empresa)
        .filter(cliente_id=cliente_id)
        .select_related("ruta", "cliente")
        .order_by("-ruta__fecha_salida", "-id")
    )
