import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timesince import timesince
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from acarreapp.tenancy import get_current_empresa
from cartera.models import PagoServicio
from cartera.services import registrar_pago_servicio, sincronizar_estado_pago
from empresa.models import Cliente
from rutas.models import Ruta

from .forms import ServicioComentarioForm, ServicioForm
from .models import Servicio


def _clientes_de_empresa(emp):
    if emp is None:
        return Cliente.objects.none()
    qs = Cliente.objects.filter(empresa=emp)
    try:
        Cliente._meta.get_field("activo")
        qs = qs.filter(activo=True)
    except Exception:
        pass
    return qs


def _configurar_form_servicio(form, emp):
    if "cliente" in form.fields:
        form.fields["cliente"].queryset = _clientes_de_empresa(emp)
    if "ruta" in form.fields:
        form.fields["ruta"].queryset = Ruta.objects.filter(empresa=emp, estado="ACTIVA") if emp else Ruta.objects.none()
    return form


def _is_gerente(user):
    role = getattr(getattr(user, "userprofile", None), "rol", "")
    return user.is_superuser or user.is_staff or role == "GERENTE"


def _is_conductor(user):
    role = getattr(getattr(user, "userprofile", None), "rol", "")
    return role == "CONDUCTOR" and not (user.is_staff or user.is_superuser)


def _can_crear_servicio(user):
    return _is_gerente(user) or _is_conductor(user)


def _servicio_de_empresa(pk):
    emp = get_current_empresa()
    if emp is None:
        raise Http404("No hay empresa activa.")
    return get_object_or_404(
        Servicio.objects.select_related("ruta", "ruta__empresa", "ruta__conductor", "cliente"),
        pk=pk,
        ruta__empresa=emp,
    )


def _can_operate_service(user, servicio):
    return _is_gerente(user) or (
        _is_conductor(user) and getattr(servicio.ruta, "conductor_id", None) == user.id
    )


class MisServiciosListView(LoginRequiredMixin, ListView):
    model = Servicio
    template_name = "servicios/mis_servicios.html"
    context_object_name = "object_list"
    paginate_by = 20

    def get_queryset(self):
        emp = get_current_empresa()
        qs = Servicio.objects.select_related("ruta", "cliente", "ruta__conductor")
        qs = qs.filter(ruta__empresa=emp) if emp else qs.none()

        if _is_conductor(self.request.user):
            qs = qs.filter(ruta__conductor=self.request.user)

        params = self.request.GET
        if params.get("solo_no_entregados") == "1" or params.get("activos") == "1":
            qs = qs.filter(entregado=False)
        if params.get("solo_rutas_activas") == "1":
            qs = qs.filter(ruta__estado="ACTIVA")
        return qs.order_by("-id")


MisServiciosView = MisServiciosListView


@login_required
@user_passes_test(_can_crear_servicio)
def crear_servicio(request):
    user = request.user
    es_conductor = _is_conductor(user)
    es_gerente = _is_gerente(user)
    emp = get_current_empresa()
    if emp is None:
        return HttpResponseForbidden("No hay empresa activa.")

    ruta_prefill = None
    initial = {}

    if es_conductor and not es_gerente:
        ruta_prefill = (
            Ruta.objects.select_related("conductor", "vehiculo")
            .filter(empresa=emp, conductor=user, estado="ACTIVA")
            .order_by("-id")
            .first()
        )
        if not ruta_prefill:
            messages.error(request, "No tienes una ruta ACTIVA asignada. No puedes agregar servicios.")
            return redirect("rutas:list")
        initial["ruta"] = ruta_prefill.pk

    ruta_id = request.GET.get("ruta")
    if ruta_id and not (es_conductor and not es_gerente):
        ruta_prefill = get_object_or_404(Ruta, pk=ruta_id, empresa=emp)
        if ruta_prefill.estado != "ACTIVA":
            messages.error(request, "Esta ruta esta CERRADA. No se pueden agregar servicios.")
            return redirect("rutas:detail", pk=ruta_prefill.pk)
        initial["ruta"] = ruta_prefill.pk

    if request.method == "POST":
        form = ServicioForm(request.POST)
        _configurar_form_servicio(form, getattr(ruta_prefill, "empresa", None) or emp)
        if form.is_valid():
            obj = form.save(commit=False)
            if ruta_prefill:
                obj.ruta = ruta_prefill
            if not getattr(obj, "ruta_id", None):
                form.add_error("ruta", "Selecciona una ruta valida.")
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": ruta_prefill})
            if obj.ruta.empresa_id != emp.id:
                return HttpResponseForbidden("Ruta no autorizada.")
            if obj.ruta.estado != "ACTIVA":
                form.add_error("ruta", "No se pueden agregar servicios a una ruta cerrada.")
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": ruta_prefill})
            if _is_conductor(user) and not _is_gerente(user) and obj.ruta.conductor_id != user.id:
                return HttpResponseForbidden("No autorizado")
            if obj.cliente and obj.cliente.empresa_id != obj.ruta.empresa_id:
                form.add_error("cliente", "El cliente no pertenece a tu empresa.")
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": ruta_prefill})

            obj.valor = obj.valor or 0
            pago_inicial = int(obj.anticipo or 0)
            if obj.estado_pago == Servicio.PAGADO:
                pago_inicial = int(obj.valor or 0)
            elif obj.estado_pago == Servicio.PENDIENTE:
                pago_inicial = 0

            try:
                with transaction.atomic():
                    obj.estado_pago = Servicio.PENDIENTE
                    obj.anticipo = 0
                    obj.save()
                    if pago_inicial > 0:
                        registrar_pago_servicio(
                            obj.pk,
                            empresa=emp,
                            usuario=user,
                            valor=pago_inicial,
                            medio_pago=PagoServicio.MEDIO_EFECTIVO,
                            observacion="Pago inicial registrado al crear el servicio.",
                        )
            except ValidationError as exc:
                form.add_error("anticipo", exc.messages[0] if hasattr(exc, "messages") else str(exc))
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": ruta_prefill})
            messages.success(request, f"Servicio #{obj.id} creado correctamente.")
            if es_conductor and not es_gerente:
                return redirect("servicios:por_ruta", ruta_id=obj.ruta_id)
            return redirect("servicios:detail", pk=obj.pk)
        messages.error(request, "Por favor revisa los campos del formulario.")
    else:
        form = ServicioForm(initial=initial)
        _configurar_form_servicio(form, getattr(ruta_prefill, "empresa", None) or emp)

    return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": ruta_prefill})


@login_required
@require_POST
def pago_efectivo_conductor(request, pk):
    servicio = _servicio_de_empresa(pk)
    if not _can_operate_service(request.user, servicio):
        return HttpResponseForbidden("No autorizado")
    if servicio.ruta.estado != "ACTIVA":
        messages.error(request, "La ruta esta cerrada.")
        return redirect("servicios:detail", pk=servicio.pk)

    try:
        monto = int(request.POST.get("monto") or "0")
    except ValueError:
        monto = 0

    try:
        pago = registrar_pago_servicio(
            servicio.pk,
            empresa=servicio.ruta.empresa,
            usuario=request.user,
            valor=monto,
            medio_pago=PagoServicio.MEDIO_EFECTIVO,
            observacion="Pago registrado desde el detalle del servicio.",
            permitir_ruta_cerrada=False,
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    else:
        if pago.movimiento_caja_id:
            messages.success(request, f"Abono de ${pago.valor:,} registrado en caja.")
        else:
            messages.success(request, f"Abono de ${pago.valor:,} registrado.")
    return redirect("servicios:detail", pk=servicio.pk)


@login_required
@user_passes_test(_is_gerente)
def editar_servicio(request, pk):
    obj = _servicio_de_empresa(pk)
    if obj.ruta.estado != "ACTIVA":
        messages.error(request, "No puedes editar servicios de una ruta CERRADA.")
        return redirect("servicios:detail", pk=obj.pk)

    if request.method == "POST":
        form = ServicioForm(request.POST, instance=obj)
        _configurar_form_servicio(form, obj.ruta.empresa)
        if form.is_valid():
            s = form.save(commit=False)
            if s.ruta.empresa_id != obj.ruta.empresa_id:
                return HttpResponseForbidden("Ruta no autorizada.")
            if s.cliente and s.cliente.empresa_id != s.ruta.empresa_id:
                form.add_error("cliente", "El cliente no pertenece a tu empresa.")
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": obj.ruta})
            total_pagado = int(obj.total_pagado or 0)
            if total_pagado > int(s.valor or 0):
                form.add_error("valor", f"El valor no puede ser menor al total pagado (${total_pagado:,}).")
                return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": obj.ruta})
            s.anticipo = total_pagado
            s.estado_pago = Servicio.PAGADO if total_pagado >= int(s.valor or 0) and int(s.valor or 0) > 0 else (
                Servicio.ANTICIPO if total_pagado > 0 else Servicio.PENDIENTE
            )
            s.save()
            sincronizar_estado_pago(s, total_pagado)
            messages.success(request, f"Servicio #{s.id} actualizado correctamente.")
            return redirect("servicios:detail", pk=s.pk)
        messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = ServicioForm(instance=obj)
        _configurar_form_servicio(form, obj.ruta.empresa)
    return render(request, "servicios/crear_servicio.html", {"form": form, "ruta_prefill": obj.ruta})


@login_required
@user_passes_test(_is_gerente)
def eliminar_servicio(request, pk):
    obj = _servicio_de_empresa(pk)
    ruta_pk = obj.ruta_id
    if obj.ruta.estado != "ACTIVA":
        messages.error(request, "No puedes eliminar servicios de una ruta cerrada.")
        return redirect("servicios:detail", pk=obj.pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Servicio eliminado.")
        return redirect("rutas:detail", pk=ruta_pk)
    return render(request, "servicios/confirmar_eliminar.html", {"obj": obj})


class ServicioDetailView(LoginRequiredMixin, DetailView):
    model = Servicio
    template_name = "servicios/detail.html"
    context_object_name = "object"

    def get_queryset(self):
        emp = get_current_empresa()
        qs = Servicio.objects.select_related("ruta", "ruta__conductor", "ruta__empresa", "cliente")
        qs = qs.filter(ruta__empresa=emp) if emp else qs.none()
        if _is_conductor(self.request.user):
            qs = qs.filter(ruta__conductor=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        s = ctx["object"]
        user = self.request.user
        es_gerente = _is_gerente(user)
        es_conductor = _is_conductor(user) and s.ruta.conductor_id == user.id
        puede_operar = _can_operate_service(user, s)

        duracion = None
        if s.recogido_en and s.entregado_en and s.entregado_en >= s.recogido_en:
            duracion = timesince(s.entregado_en, s.recogido_en)

        distancia_km = None
        if all([s.lat_recogida, s.lon_recogida, s.lat_entrega, s.lon_entrega]):
            radius = 6371.0
            lat1 = math.radians(s.lat_recogida)
            lon1 = math.radians(s.lon_recogida)
            lat2 = math.radians(s.lat_entrega)
            lon2 = math.radians(s.lon_entrega)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            distancia_km = round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

        directions_url = None
        if all([s.lat_recogida, s.lon_recogida, s.lat_entrega, s.lon_entrega]):
            directions_url = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={s.lat_recogida},{s.lon_recogida}"
                f"&destination={s.lat_entrega},{s.lon_entrega}"
            )

        ctx.update(
            {
                "es_gerente": es_gerente,
                "es_conductor": es_conductor,
                "puede_marcar_recogido": puede_operar and not s.recogido,
                "puede_marcar_entregado": puede_operar and s.recogido and not s.entregado,
                "puede_registrar_efectivo": puede_operar and s.estado_pago != Servicio.PAGADO,
                "max_pago": s.saldo_cartera,
                "pagos_servicio": s.pagos.select_related(
                    "registrado_por", "movimiento_caja", "movimiento_reversion"
                ).order_by("-fecha_pago", "-creado_en"),
                "duracion": duracion,
                "distancia_km": distancia_km,
                "directions_url": directions_url,
            }
        )
        return ctx


@login_required
@require_POST
def marcar_recogido(request, pk):
    servicio = _servicio_de_empresa(pk)
    if not _can_operate_service(request.user, servicio):
        return HttpResponseForbidden("No autorizado")
    if servicio.ruta.estado != "ACTIVA":
        messages.error(request, "La ruta esta cerrada.")
        return redirect("servicios:detail", pk=pk)
    servicio.marcar_recogido(request.POST.get("lat"), request.POST.get("lon"))
    servicio.save(update_fields=["recogido", "recogido_en", "lat_recogida", "lon_recogida"])
    messages.success(request, "Servicio marcado como recogido.")
    return redirect("servicios:detail", pk=pk)


@login_required
@require_POST
def marcar_entregado(request, pk):
    servicio = _servicio_de_empresa(pk)
    if not _can_operate_service(request.user, servicio):
        return HttpResponseForbidden("No autorizado")
    if servicio.ruta.estado != "ACTIVA":
        messages.error(request, "La ruta esta cerrada.")
        return redirect("servicios:detail", pk=pk)
    servicio.marcar_entregado(request.POST.get("lat"), request.POST.get("lon"))
    servicio.save(update_fields=["entregado", "entregado_en", "lat_entrega", "lon_entrega"])
    messages.success(request, "Servicio marcado como entregado.")
    return redirect("servicios:detail", pk=pk)


@login_required
@user_passes_test(_is_gerente)
@require_POST
def marcar_pagado_gerente(request, pk):
    servicio = _servicio_de_empresa(pk)
    if servicio.ruta.estado != "ACTIVA":
        messages.error(request, "La ruta esta cerrada.")
        return redirect("servicios:detail", pk=servicio.pk)
    saldo = servicio.saldo_cartera
    if saldo <= 0:
        messages.info(request, "Este servicio ya esta pagado.")
        return redirect("servicios:detail", pk=servicio.pk)
    try:
        registrar_pago_servicio(
            servicio.pk,
            empresa=servicio.ruta.empresa,
            usuario=request.user,
            valor=saldo,
            medio_pago=PagoServicio.MEDIO_AJUSTE,
            observacion="Pago total registrado desde accion rapida de gerencia.",
            permitir_ruta_cerrada=False,
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    else:
        messages.success(request, f"Servicio #{servicio.id} registrado como pagado.")
    return redirect("servicios:detail", pk=servicio.pk)


@login_required
@require_POST
def comentar_servicio(request, pk):
    servicio = _servicio_de_empresa(pk)
    if _is_conductor(request.user) and servicio.ruta.conductor_id != request.user.id:
        return HttpResponseForbidden("No autorizado")

    form = ServicioComentarioForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.servicio = servicio
        comentario.autor = request.user
        comentario.save()
        messages.success(request, "Comentario agregado.")
    else:
        messages.error(request, "No se pudo agregar el comentario.")
    return redirect("servicios:detail", pk=servicio.pk)


class ServiciosPorRutaView(LoginRequiredMixin, ListView):
    model = Servicio
    template_name = "servicios/list_por_ruta.html"
    context_object_name = "servicios"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        emp = get_current_empresa()
        if emp is None:
            raise Http404("No hay empresa activa.")
        self.ruta = get_object_or_404(
            Ruta.objects.select_related("conductor", "vehiculo"),
            pk=kwargs["ruta_id"],
            empresa=emp,
        )
        if _is_conductor(request.user) and self.ruta.conductor_id != request.user.id:
            messages.error(request, "No autorizado para ver esta ruta.")
            return redirect("rutas:list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Servicio.objects.select_related("cliente", "ruta")
            .filter(ruta=self.ruta)
            .order_by("orden", "id")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "ruta": self.ruta,
                "es_conductor": _is_conductor(self.request.user) and self.ruta.conductor_id == self.request.user.id,
                "es_gerente": _is_gerente(self.request.user),
            }
        )
        return ctx


@login_required
def list_por_ruta(request, ruta_id: int):
    emp = get_current_empresa()
    if emp is None:
        raise Http404("No hay empresa activa.")
    ruta = get_object_or_404(Ruta, pk=ruta_id, empresa=emp)
    if _is_conductor(request.user) and ruta.conductor_id != request.user.id:
        return HttpResponseForbidden("No autorizado")
    servicios = Servicio.objects.select_related("cliente").filter(ruta=ruta).order_by("orden", "id")
    return render(
        request,
        "servicios/list_por_ruta.html",
        {
            "ruta": ruta,
            "servicios": servicios,
            "es_gerente": _is_gerente(request.user),
            "es_conductor": _is_conductor(request.user) and ruta.conductor_id == request.user.id,
        },
    )
