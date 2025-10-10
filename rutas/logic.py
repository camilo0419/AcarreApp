# rutas/logic.py
from django.db import transaction
from django.db.models import Sum

from .models import CierreRuta
from rutas.models import MovimientoCaja

try:
    from acarreapp.tenancy import get_current_empresa
except Exception:
    get_current_empresa = None


@transaction.atomic
def cerrar_ruta(ruta, user):
    """
    Calcula y persiste el CierreRuta de 'ruta'.
    Guarda SOLO los campos que existen en tu modelo CierreRuta.
    No intenta guardar 'total_valor_servicios' ni 'caja_disponible'.
    """
    # Empresa (obligatoria por tu FK NOT NULL)
    empresa = getattr(ruta, "empresa", None)
    if empresa is None and callable(get_current_empresa):
        empresa = get_current_empresa()
    if empresa is None:
        raise ValueError(
            "No se pudo resolver 'empresa' para CierreRuta. "
            "Asegura que Ruta.empresa existe o que acarreapp.tenancy.get_current_empresa() retorne una empresa."
        )

    # Totales de servicios
    servicios_qs = ruta.servicios.all()
    total_servicios = servicios_qs.count()

    # “Cobrado por conductor” (ajusta si tu lógica es distinta)
    total_cobrado = servicios_qs.filter(estado_pago="PAG").aggregate(s=Sum("valor"))["s"] or 0

    # Si tu modelo NO tiene 'total_valor_servicios', no lo guardamos.
    total_valor_servicios_calc = servicios_qs.aggregate(s=Sum("valor"))["s"] or 0
    total_pendiente = total_valor_servicios_calc - (total_cobrado or 0)

    # Caja (ingresos/gastos de la ruta)
    if hasattr(ruta, "movimientos"):
        movs = ruta.movimientos.all()
    else:
        movs = MovimientoCaja.objects.filter(ruta=ruta)

    total_ingresos = movs.filter(tipo="INGRESO").aggregate(s=Sum("valor"))["s"] or 0
    total_gastos   = movs.filter(tipo="GASTO").aggregate(s=Sum("valor"))["s"] or 0
    # caja_disponible = total_ingresos - total_gastos  # → NO se persiste si el campo no existe

    # Crear/actualizar CierreRuta SOLO con campos existentes
    cierre, created = CierreRuta.objects.get_or_create(
        ruta=ruta,
        empresa=empresa,
        defaults={
            "total_servicios": total_servicios,
            "total_cobrado": total_cobrado,
            "total_pendiente": total_pendiente,
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "generado_por": user,
        },
    )

    if not created:
        cierre.total_servicios = total_servicios
        cierre.total_cobrado = total_cobrado
        cierre.total_pendiente = total_pendiente
        cierre.total_ingresos = total_ingresos
        cierre.total_gastos = total_gastos
        cierre.generado_por = user
        cierre.save(update_fields=[
            "total_servicios",
            "total_cobrado",
            "total_pendiente",
            "total_ingresos",
            "total_gastos",
            "generado_por",
        ])

    # Si tu flujo requiere cerrar la ruta aquí, mantenlo:
    if ruta.estado != "CERRADA":
        ruta.estado = "CERRADA"
        ruta.save(update_fields=["estado"])

    return cierre
