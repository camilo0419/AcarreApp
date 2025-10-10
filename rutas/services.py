from decimal import Decimal
from django.db import transaction
from .models import CierreRuta, Ruta
from servicios.models import Servicio

@transaction.atomic
def cerrar_ruta(ruta: Ruta, usuario):
    servicios = ruta.servicios.all()

    total_servicios = servicios.count()
    total_cobrado = sum((s.valor for s in servicios if s.estado_pago == Servicio.PAGADO), Decimal("0"))
    total_pendiente = sum((s.valor for s in servicios if s.estado_pago == Servicio.PENDIENTE), Decimal("0"))

    movs = ruta.movimientos.all()
    total_gastos = sum((m.valor for m in movs if m.tipo == 'GASTO'), Decimal("0"))
    total_ingresos = (ruta.base_efectivo or Decimal("0")) + sum((m.valor for m in movs if m.tipo == 'INGRESO'), Decimal("0"))

    utilidad_neta = total_cobrado - total_gastos

    cierre, _ = CierreRuta.objects.update_or_create(
        ruta=ruta,
        defaults={
            # ⬅️ esto faltaba:
            'empresa': ruta.empresa,
            'total_servicios': total_servicios,
            'total_cobrado': total_cobrado,
            'total_pendiente': total_pendiente,
            'total_gastos': total_gastos,
            'total_ingresos': total_ingresos,
            'utilidad_neta': utilidad_neta,
            'generado_por': usuario,
        }
    )

    ruta.estado = 'CERRADA'
    ruta.save(update_fields=['estado'])
    return cierre
