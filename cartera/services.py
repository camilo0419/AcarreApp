from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from rutas.models import MovimientoCaja
from servicios.models import Servicio

from .models import CarteraEmpresaConfig, CuentaCobro, PagoServicio


def obtener_config_cartera(empresa):
    config, _ = CarteraEmpresaConfig.objects.get_or_create(
        empresa=empresa,
        defaults={
            "nombre_emisor": empresa.nombre,
            "nit_emisor": getattr(empresa, "nit", ""),
        },
    )
    return config


def total_pagado_servicio(servicio):
    pagos = PagoServicio.objects.filter(servicio=servicio, anulado=False)
    if pagos.exists():
        return int(pagos.aggregate(total=Sum("valor"))["total"] or 0)
    return int(servicio.anticipo or 0)


def estado_pago_para(valor_servicio, total_pagado):
    valor_servicio = int(valor_servicio or 0)
    total_pagado = int(total_pagado or 0)
    if valor_servicio > 0 and total_pagado >= valor_servicio:
        return Servicio.PAGADO
    if total_pagado > 0:
        return Servicio.ANTICIPO
    return Servicio.PENDIENTE


def sincronizar_estado_pago(servicio, total_pagado=None):
    if total_pagado is None:
        total_pagado = total_pagado_servicio(servicio)
    total_pagado = min(int(total_pagado or 0), int(servicio.valor or 0))
    servicio.anticipo = total_pagado
    servicio.estado_pago = estado_pago_para(servicio.valor, total_pagado)
    servicio.save(update_fields=["anticipo", "estado_pago"])
    return servicio


def _crear_pago_legacy_si_falta(servicio):
    anticipo = int(servicio.anticipo or 0)
    if anticipo <= 0:
        return
    if PagoServicio.objects.filter(servicio=servicio).exists():
        return
    valor = min(anticipo, int(servicio.valor or 0))
    if valor <= 0:
        return
    PagoServicio.objects.create(
        empresa=servicio.ruta.empresa,
        servicio=servicio,
        cliente=servicio.cliente,
        ruta=servicio.ruta,
        valor=valor,
        medio_pago=PagoServicio.MEDIO_ANTICIPO,
        fecha_pago=servicio.ruta.fecha_salida,
        observacion="Pago migrado desde el anticipo historico del servicio.",
        impacta_caja=False,
    )


def _sumar_pagos_bloqueados(servicio):
    return int(
        PagoServicio.objects.select_for_update()
        .filter(servicio=servicio, anulado=False)
        .aggregate(total=Sum("valor"))["total"]
        or 0
    )


@transaction.atomic
def registrar_pago_servicio(
    servicio_id,
    *,
    empresa,
    usuario,
    valor,
    medio_pago=PagoServicio.MEDIO_EFECTIVO,
    fecha_pago=None,
    referencia="",
    observacion="",
    permitir_ruta_cerrada=True,
):
    servicio = (
        Servicio.objects.select_for_update()
        .select_related("ruta", "ruta__empresa", "cliente")
        .get(pk=servicio_id, ruta__empresa=empresa)
    )
    if servicio.ruta.estado != "ACTIVA" and not permitir_ruta_cerrada:
        raise ValidationError("La ruta esta cerrada.")

    try:
        valor = int(valor)
    except (TypeError, ValueError):
        raise ValidationError("El valor del pago no es valido.")
    if valor <= 0:
        raise ValidationError("El valor del pago debe ser positivo.")

    _crear_pago_legacy_si_falta(servicio)
    total_actual = _sumar_pagos_bloqueados(servicio)
    saldo = max(int(servicio.valor or 0) - total_actual, 0)
    if saldo <= 0:
        raise ValidationError("Este servicio ya esta pagado.")
    if valor > saldo:
        raise ValidationError("El pago no puede superar el saldo pendiente.")

    impacta_caja = servicio.ruta.estado == "ACTIVA"
    pago = PagoServicio.objects.create(
        empresa=empresa,
        servicio=servicio,
        cliente=servicio.cliente,
        ruta=servicio.ruta,
        valor=valor,
        medio_pago=medio_pago,
        fecha_pago=fecha_pago or timezone.localdate(),
        referencia=(referencia or "").strip(),
        observacion=(observacion or "").strip(),
        registrado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        impacta_caja=impacta_caja,
    )

    if impacta_caja:
        cliente_nombre = getattr(servicio.cliente, "nombre", "Cliente sin nombre")
        trayecto = f" ({servicio.origen or '-'} -> {servicio.destino or '-'})" if (
            servicio.origen or servicio.destino
        ) else ""
        movimiento = MovimientoCaja.objects.create(
            empresa=empresa,
            ruta=servicio.ruta,
            tipo="INGRESO",
            concepto=f"Pago cartera servicio #{servicio.id} - {cliente_nombre}{trayecto}",
            valor=valor,
            usuario=usuario,
        )
        pago.movimiento_caja = movimiento
        pago.save(update_fields=["movimiento_caja"])

    sincronizar_estado_pago(servicio, total_actual + valor)
    return pago


@transaction.atomic
def anular_pago_servicio(pago_id, *, empresa, usuario, motivo):
    pago = (
        PagoServicio.objects.select_for_update()
        .select_related("servicio", "ruta", "cliente", "empresa", "movimiento_caja")
        .get(pk=pago_id, empresa=empresa)
    )
    if pago.anulado:
        raise ValidationError("El pago ya estaba anulado.")
    if pago.movimiento_caja_id and pago.ruta.estado != "ACTIVA":
        raise ValidationError("No se puede anular un pago de caja cuando la ruta ya esta cerrada.")

    pago.anulado = True
    pago.anulado_por = usuario if getattr(usuario, "is_authenticated", False) else None
    pago.anulado_en = timezone.now()
    pago.motivo_anulacion = (motivo or "").strip()

    if pago.movimiento_caja_id:
        movimiento = MovimientoCaja.objects.create(
            empresa=empresa,
            ruta=pago.ruta,
            tipo="GASTO",
            concepto=f"Reversion pago cartera #{pago.id}",
            valor=pago.valor,
            usuario=usuario,
        )
        pago.movimiento_reversion = movimiento

    pago.save(
        update_fields=[
            "anulado",
            "anulado_por",
            "anulado_en",
            "motivo_anulacion",
            "movimiento_reversion",
        ]
    )
    total_actual = _sumar_pagos_bloqueados(pago.servicio)
    sincronizar_estado_pago(pago.servicio, total_actual)
    return pago


@transaction.atomic
def obtener_o_crear_cuenta_cobro(servicio, usuario=None):
    cuenta = CuentaCobro.objects.filter(servicio=servicio, empresa=servicio.ruta.empresa).first()
    if cuenta:
        return cuenta

    config = obtener_config_cartera(servicio.ruta.empresa)
    config = CarteraEmpresaConfig.objects.select_for_update().get(pk=config.pk)
    consecutivo = config.proximo_consecutivo
    numero = f"{config.prefijo_cuenta_cobro}-{consecutivo:06d}"
    cuenta = CuentaCobro.objects.create(
        empresa=servicio.ruta.empresa,
        servicio=servicio,
        cliente=servicio.cliente,
        consecutivo=consecutivo,
        numero=numero,
        emitida_por=usuario if getattr(usuario, "is_authenticated", False) else None,
    )
    config.proximo_consecutivo = consecutivo + 1
    config.save(update_fields=["proximo_consecutivo", "actualizado_en"])
    return cuenta
