from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from acarreapp.tenancy import get_current_empresa
from empresa.models import Cliente
from servicios.models import Servicio

from .forms import AnularPagoForm, CarteraEmpresaConfigForm, PagoServicioForm
from .models import CuentaCobro, PagoServicio
from .pdf import PDFDependencyError, render_pdf_response
from .services import (
    anotar_finanzas_servicios,
    anular_pago_servicio,
    emitir_cuenta_cobro,
    obtener_config_cartera,
    obtener_cuenta_cobro,
    registrar_pago_servicio,
    servicios_con_saldo,
)


def _is_gerente(user):
    role = getattr(getattr(user, "userprofile", None), "rol", "")
    return user.is_superuser or user.is_staff or role == "GERENTE"


def gerente_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_gerente(request.user):
            return HttpResponseForbidden("No autorizado")
        return view_func(request, *args, **kwargs)

    return wrapper


def _empresa_or_404():
    empresa = get_current_empresa()
    if empresa is None:
        raise Http404("No hay empresa activa.")
    return empresa


def _servicios_empresa_qs(empresa):
    return Servicio.objects.filter(ruta__empresa=empresa).select_related(
        "cliente",
        "ruta",
        "ruta__conductor",
        "ruta__vehiculo",
    )


def _servicios_con_saldo_qs(empresa):
    return servicios_con_saldo(_servicios_empresa_qs(empresa))


def _filtrar_servicios_base(qs, params):
    cliente_id = params.get("cliente")
    if cliente_id and cliente_id.isdigit():
        qs = qs.filter(cliente_id=int(cliente_id))

    conductor_id = params.get("conductor")
    if conductor_id and conductor_id.isdigit():
        qs = qs.filter(ruta__conductor_id=int(conductor_id))

    ruta_estado = (params.get("ruta_estado") or "").strip()
    if ruta_estado in {"ACTIVA", "CERRADA"}:
        qs = qs.filter(ruta__estado=ruta_estado)

    desde = (params.get("desde") or "").strip()
    hasta = (params.get("hasta") or "").strip()
    if desde:
        qs = qs.filter(ruta__fecha_salida__gte=desde)
    if hasta:
        qs = qs.filter(ruta__fecha_salida__lte=hasta)

    q = (params.get("q") or "").strip()
    if q:
        base = (
            Q(cliente__nombre__icontains=q)
            | Q(origen__icontains=q)
            | Q(destino__icontains=q)
            | Q(ruta__nombre__icontains=q)
        )
        if q.isdigit():
            base |= Q(id=int(q)) | Q(ruta_id=int(q))
        qs = qs.filter(base)
    return qs


def _filtros_context(empresa):
    servicios = _servicios_empresa_qs(empresa)
    return {
        "filtros_clientes": Cliente.objects.filter(empresa=empresa).order_by("nombre"),
        "filtros_conductores": (
            servicios.values("ruta__conductor__id", "ruta__conductor__username")
            .annotate(n=Count("id"))
            .order_by("ruta__conductor__username")
        ),
    }


def _aging(servicios):
    hoy = timezone.localdate()
    buckets = {"b0_30": 0, "b31_60": 0, "b61_90": 0, "b90_mas": 0}
    for servicio in servicios:
        saldo = int(servicio.saldo_cartera or 0)
        if saldo <= 0:
            continue
        dias = (hoy - servicio.ruta.fecha_salida).days if servicio.ruta.fecha_salida else 0
        if dias <= 30:
            buckets["b0_30"] += saldo
        elif dias <= 60:
            buckets["b31_60"] += saldo
        elif dias <= 90:
            buckets["b61_90"] += saldo
        else:
            buckets["b90_mas"] += saldo
    return buckets


def _top_clientes(servicios):
    rows = defaultdict(lambda: {"cliente__id": None, "cliente__nombre": "", "total": 0, "servicios": 0})
    for servicio in servicios:
        saldo = int(servicio.saldo_cartera or 0)
        if saldo <= 0:
            continue
        row = rows[servicio.cliente_id]
        row["cliente__id"] = servicio.cliente_id
        row["cliente__nombre"] = servicio.cliente.nombre
        row["total"] += saldo
        row["servicios"] += 1
    return sorted(rows.values(), key=lambda item: item["total"], reverse=True)


@gerente_required
def dashboard(request):
    empresa = _empresa_or_404()
    servicios = list(anotar_finanzas_servicios(_servicios_empresa_qs(empresa)))
    cartera = [servicio for servicio in servicios if servicio.saldo_cartera > 0]

    hoy = timezone.localdate()
    primer_dia_mes = date(hoy.year, hoy.month, 1)
    pagos_mes = (
        PagoServicio.objects.filter(empresa=empresa, anulado=False, fecha_pago__gte=primer_dia_mes)
        .aggregate(total=Coalesce(Sum("valor"), 0))["total"]
        or 0
    )

    contexto = {
        "empresa": empresa,
        "total_cartera": sum(int(s.saldo_cartera or 0) for s in cartera),
        "total_facturado": sum(int(s.valor or 0) for s in servicios),
        "total_pagado": sum(int(s.total_pagado or 0) for s in servicios),
        "pagos_mes": int(pagos_mes),
        "clientes_con_saldo": len({s.cliente_id for s in cartera}),
        "servicios_con_saldo": len(cartera),
        "top_clientes": _top_clientes(cartera)[:8],
        "servicios_recientes": sorted(cartera, key=lambda s: (s.ruta.fecha_salida, s.id), reverse=True)[:10],
        "pagos_recientes": (
            PagoServicio.objects.filter(empresa=empresa)
            .select_related("cliente", "servicio", "registrado_por")
            .order_by("-creado_en")[:8]
        ),
        "aging": _aging(cartera),
    }
    return render(request, "cartera/dashboard.html", contexto)


@gerente_required
def clientes_list(request):
    empresa = _empresa_or_404()
    cartera_qs = _servicios_con_saldo_qs(empresa)
    q = (request.GET.get("q") or "").strip()
    if q:
        cartera_qs = cartera_qs.filter(Q(cliente__nombre__icontains=q) | Q(cliente__contacto__icontains=q))
    servicios = list(cartera_qs)
    rows = _top_clientes(servicios)
    contexto = {
        "empresa": empresa,
        "total_general": sum(int(s.saldo_cartera or 0) for s in servicios),
        "por_cliente": rows,
        "q": q,
    }
    return render(request, "cartera/clientes_list.html", contexto)


@gerente_required
def pendientes(request):
    return clientes_list(request)


@gerente_required
def cliente_detalle(request, cliente_id: int):
    empresa = _empresa_or_404()
    cliente = get_object_or_404(Cliente, id=cliente_id, empresa=empresa)
    servicios = list(
        _servicios_con_saldo_qs(empresa)
        .filter(cliente=cliente)
        .order_by("-ruta__fecha_salida", "-id")
    )
    pagos = (
        PagoServicio.objects.filter(empresa=empresa, cliente=cliente)
        .select_related("servicio", "ruta", "registrado_por")
        .order_by("-fecha_pago", "-creado_en")
    )
    cuentas_emitidas = set(
        CuentaCobro.objects.filter(empresa=empresa, cliente=cliente).values_list("servicio_id", flat=True)
    )
    contexto = {
        "empresa": empresa,
        "cliente": cliente,
        "servicios": servicios,
        "pagos": pagos,
        "cuentas_emitidas": cuentas_emitidas,
        "total_cliente": sum(int(s.saldo_cartera or 0) for s in servicios),
    }
    return render(request, "cartera/cliente_detalle.html", contexto)


@gerente_required
def servicios_list(request):
    empresa = _empresa_or_404()
    qs = _filtrar_servicios_base(_servicios_con_saldo_qs(empresa), request.GET).order_by("-ruta__fecha_salida", "-id")
    servicios = list(qs)
    estado = (request.GET.get("estado") or "").strip()
    if estado in {Servicio.PENDIENTE, Servicio.PARCIAL, Servicio.PAGADO}:
        servicios = [servicio for servicio in servicios if servicio.estado_pago == estado]
    contexto = {
        "empresa": empresa,
        "servicios": servicios,
        "total_saldo": sum(int(s.saldo_cartera or 0) for s in servicios),
        **_filtros_context(empresa),
    }
    return render(request, "cartera/servicios_list.html", contexto)


@gerente_required
def registrar_pago(request, servicio_id: int):
    empresa = _empresa_or_404()
    servicio = get_object_or_404(anotar_finanzas_servicios(_servicios_empresa_qs(empresa)), pk=servicio_id)
    saldo = int(servicio.saldo_cartera or 0)

    if request.method == "POST":
        form = PagoServicioForm(request.POST, saldo=saldo)
        if form.is_valid():
            try:
                pago = registrar_pago_servicio(
                    servicio.pk,
                    empresa=empresa,
                    usuario=request.user,
                    valor=form.cleaned_data["valor"],
                    medio_pago=form.cleaned_data["medio_pago"],
                    fecha_pago=form.cleaned_data["fecha_pago"],
                    referencia=form.cleaned_data["referencia"],
                    observacion=form.cleaned_data["observacion"],
                )
            except ValidationError as exc:
                form.add_error("valor", exc.messages[0] if hasattr(exc, "messages") else str(exc))
            else:
                if pago.movimiento_caja_id:
                    messages.success(request, "Pago registrado y asociado a caja de ruta.")
                else:
                    messages.success(request, "Pago registrado sin modificar caja porque la ruta esta cerrada.")
                return redirect("cartera:cliente_detalle", cliente_id=servicio.cliente_id)
    else:
        form = PagoServicioForm(saldo=saldo)

    return render(
        request,
        "cartera/pago_form.html",
        {"empresa": empresa, "servicio": servicio, "saldo": saldo, "form": form},
    )


@gerente_required
def pagos_list(request):
    empresa = _empresa_or_404()
    pagos = PagoServicio.objects.filter(empresa=empresa).select_related(
        "cliente", "servicio", "ruta", "registrado_por", "movimiento_caja"
    )
    estado = (request.GET.get("estado") or "").strip()
    if estado == "activos":
        pagos = pagos.filter(anulado=False)
    elif estado == "anulados":
        pagos = pagos.filter(anulado=True)
    desde = (request.GET.get("desde") or "").strip()
    hasta = (request.GET.get("hasta") or "").strip()
    if desde:
        pagos = pagos.filter(fecha_pago__gte=desde)
    if hasta:
        pagos = pagos.filter(fecha_pago__lte=hasta)
    q = (request.GET.get("q") or "").strip()
    if q:
        base = Q(cliente__nombre__icontains=q) | Q(referencia__icontains=q) | Q(observacion__icontains=q)
        if q.isdigit():
            base |= Q(servicio_id=int(q)) | Q(id=int(q))
        pagos = pagos.filter(base)

    return render(
        request,
        "cartera/pagos_list.html",
        {
            "empresa": empresa,
            "pagos": pagos.order_by("-fecha_pago", "-creado_en"),
            "anular_form": AnularPagoForm(),
            "total_pagos": int(pagos.filter(anulado=False).aggregate(total=Coalesce(Sum("valor"), 0))["total"] or 0),
        },
    )


@gerente_required
@require_POST
def anular_pago(request, pago_id: int):
    empresa = _empresa_or_404()
    form = AnularPagoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Debes indicar un motivo de anulacion.")
        return redirect("cartera:pagos_list")
    try:
        anular_pago_servicio(pago_id, empresa=empresa, usuario=request.user, motivo=form.cleaned_data["motivo"])
    except (PagoServicio.DoesNotExist, ValidationError) as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    else:
        messages.success(request, "Pago anulado con trazabilidad.")
    return redirect("cartera:pagos_list")


@gerente_required
def configuracion(request):
    empresa = _empresa_or_404()
    config = obtener_config_cartera(empresa)
    if request.method == "POST":
        form = CarteraEmpresaConfigForm(request.POST, instance=config, empresa=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuracion de cartera actualizada.")
            return redirect("cartera:configuracion")
    else:
        form = CarteraEmpresaConfigForm(instance=config, empresa=empresa)
    return render(request, "cartera/configuracion.html", {"empresa": empresa, "form": form, "config": config})


@gerente_required
def estado_cuenta_pdf(request, cliente_id: int):
    empresa = _empresa_or_404()
    cliente = get_object_or_404(Cliente, id=cliente_id, empresa=empresa)
    servicios = list(
        _servicios_con_saldo_qs(empresa).filter(cliente=cliente).order_by("-ruta__fecha_salida", "-id")
    )
    pagos = (
        PagoServicio.objects.filter(empresa=empresa, cliente=cliente, anulado=False)
        .select_related("servicio", "ruta")
        .order_by("-fecha_pago", "-creado_en")
    )
    config = obtener_config_cartera(empresa)
    contexto = {
        "empresa": empresa,
        "config": config,
        "cliente": cliente,
        "servicios": servicios,
        "pagos": pagos,
        "emitido_en": timezone.localtime(),
        "total_saldo": sum(int(s.saldo_cartera or 0) for s in servicios),
        "total_facturado": sum(int(s.valor or 0) for s in servicios),
        "total_pagado": sum(int(s.total_pagado or 0) for s in servicios),
    }
    try:
        return render_pdf_response(
            request,
            "cartera/pdf/estado_cuenta.html",
            contexto,
            f"estado_cuenta_{cliente.nombre}_{timezone.localdate()}",
        )
    except PDFDependencyError as exc:
        return HttpResponse(str(exc), status=503)


@gerente_required
@require_POST
def emitir_cuenta_cobro_view(request, servicio_id: int):
    empresa = _empresa_or_404()
    servicio = get_object_or_404(_servicios_empresa_qs(empresa), pk=servicio_id)
    cuenta = emitir_cuenta_cobro(servicio, request.user)
    messages.success(request, f"Cuenta de cobro {cuenta.numero} emitida.")
    return redirect("cartera:cuenta_cobro_pdf", servicio_id=servicio.id)


@gerente_required
def cuenta_cobro_pdf(request, servicio_id: int):
    empresa = _empresa_or_404()
    servicio = get_object_or_404(anotar_finanzas_servicios(_servicios_empresa_qs(empresa)), pk=servicio_id)
    cuenta = obtener_cuenta_cobro(servicio)
    if cuenta is None:
        raise Http404("La cuenta de cobro no ha sido emitida.")
    pagos = servicio.pagos.filter(anulado=False).order_by("-fecha_pago", "-creado_en")
    config = obtener_config_cartera(empresa)
    contexto = {
        "empresa": empresa,
        "config": config,
        "servicio": servicio,
        "cliente": servicio.cliente,
        "cuenta": cuenta,
        "pagos": pagos,
        "emitido_en": timezone.localtime(),
        "saldo": int(servicio.saldo_cartera or 0),
        "total_pagado": int(servicio.total_pagado or 0),
    }
    try:
        return render_pdf_response(
            request,
            "cartera/pdf/cuenta_cobro.html",
            contexto,
            f"cuenta_cobro_{cuenta.numero}_servicio_{servicio.id}",
        )
    except PDFDependencyError as exc:
        return HttpResponse(str(exc), status=503)
