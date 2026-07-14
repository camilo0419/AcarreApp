from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from rutas.models import MovimientoCaja
from servicios.models import Servicio

from .models import CarteraEmpresaConfig, CuentaCobro, PagoServicio

TOTAL_PAGADO_ANNOTATION = "total_pagado_calc"
SALDO_CARTERA_ANNOTATION = "saldo_cartera_calc"


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
    annotated = getattr(servicio, TOTAL_PAGADO_ANNOTATION, None)
    if annotated is not None:
        return int(annotated or 0)
    return int(
        PagoServicio.objects.filter(servicio=servicio, anulado=False).aggregate(total=Sum("valor"))["total"] or 0
    )


def saldo_servicio(servicio):
    annotated = getattr(servicio, SALDO_CARTERA_ANNOTATION, None)
    if annotated is not None:
        return max(int(annotated or 0), 0)
    return max(int(servicio.valor or 0) - total_pagado_servicio(servicio), 0)


def estado_pago_para(valor_servicio, total_pagado):
    valor_servicio = int(valor_servicio or 0)
    total_pagado = int(total_pagado or 0)
    if total_pagado <= 0:
        return Servicio.PENDIENTE
    if valor_servicio > 0 and total_pagado >= valor_servicio:
        return Servicio.PAGADO
    return Servicio.PARCIAL


def estado_pago_servicio(servicio):
    return estado_pago_para(servicio.valor, total_pagado_servicio(servicio))


def anotar_finanzas_servicios(qs):
    return qs.annotate(
        **{
            TOTAL_PAGADO_ANNOTATION: Coalesce(
                Sum("pagos__valor", filter=Q(pagos__anulado=False)),
                Value(0),
                output_field=IntegerField(),
            )
        }
    ).annotate(
        **{
            SALDO_CARTERA_ANNOTATION: F("valor") - F(TOTAL_PAGADO_ANNOTATION),
        }
    )


def servicios_con_saldo(qs):
    return anotar_finanzas_servicios(qs).filter(**{f"{SALDO_CARTERA_ANNOTATION}__gt": 0})


def _sumar_pagos_bloqueados(servicio):
    return int(
        PagoServicio.objects.select_for_update()
        .filter(servicio=servicio, anulado=False)
        .aggregate(total=Sum("valor"))["total"]
        or 0
    )


def validar_sin_sobrepago(servicio, total_pagado=None):
    total_pagado = total_pagado_servicio(servicio) if total_pagado is None else int(total_pagado or 0)
    if total_pagado > int(servicio.valor or 0):
        raise ValidationError("El total pagado no puede superar el valor del servicio.")


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

    validar_sin_sobrepago(servicio, total_actual + valor)
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
    validar_sin_sobrepago(pago.servicio)
    return pago


def obtener_cuenta_cobro(servicio):
    return CuentaCobro.objects.filter(servicio=servicio, empresa=servicio.ruta.empresa).first()


@transaction.atomic
def emitir_cuenta_cobro(servicio, usuario=None):
    cuenta = CuentaCobro.objects.select_for_update().filter(
        servicio=servicio, empresa=servicio.ruta.empresa
    ).first()
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
