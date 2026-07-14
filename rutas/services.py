from dataclasses import dataclass

from django.db import transaction
from django.db.models import Sum

from servicios.models import Servicio

from .models import CierreRuta, MovimientoCaja, Ruta


@dataclass
class CierreCalculado:
    empresa: object
    ruta: Ruta
    total_servicios: int
    total_cobrado: int
    total_pendiente: int
    total_gastos: int
    total_ingresos: int
    utilidad_neta: int
    generado_por: object | None = None


def calcular_cierre_ruta(ruta: Ruta, usuario=None) -> CierreCalculado:
    servicios = list(ruta.servicios.select_related("cliente"))
    total_servicios = len(servicios)
    total_cobrado = sum(int(s.anticipo or 0) for s in servicios)
    total_pendiente = sum(int(getattr(s, "saldo_cartera", 0) or 0) for s in servicios)

    movs = MovimientoCaja.objects.filter(ruta=ruta)
    total_gastos = int(movs.filter(tipo="GASTO").aggregate(s=Sum("valor"))["s"] or 0)
    ingresos_mov = int(movs.filter(tipo="INGRESO").aggregate(s=Sum("valor"))["s"] or 0)
    total_ingresos = int(ruta.base_efectivo or 0) + ingresos_mov
    utilidad_neta = total_cobrado - total_gastos

    return CierreCalculado(
        empresa=ruta.empresa,
        ruta=ruta,
        total_servicios=total_servicios,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        total_gastos=total_gastos,
        total_ingresos=total_ingresos,
        utilidad_neta=utilidad_neta,
        generado_por=usuario,
    )


@transaction.atomic
def cerrar_ruta(ruta: Ruta, usuario):
    locked = Ruta.objects.select_for_update().select_related("empresa").get(pk=ruta.pk)
    calculo = calcular_cierre_ruta(locked, usuario)

    cierre, _ = CierreRuta.objects.update_or_create(
        ruta=locked,
        defaults={
            "empresa": locked.empresa,
            "total_servicios": calculo.total_servicios,
            "total_cobrado": calculo.total_cobrado,
            "total_pendiente": calculo.total_pendiente,
            "total_gastos": calculo.total_gastos,
            "total_ingresos": calculo.total_ingresos,
            "utilidad_neta": calculo.utilidad_neta,
            "generado_por": usuario,
        },
    )

    if locked.estado != "CERRADA":
        locked.estado = "CERRADA"
        locked.save(update_fields=["estado"])

    return cierre
