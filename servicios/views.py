# servicios/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView
from django.utils import timezone
from django.utils.timesince import timesince
from django.http import HttpResponseForbidden
from .forms import ServicioForm, ServicioComentarioForm
from .models import Servicio, ServicioComentario
from rutas.models import Ruta, MovimientoCaja
from acarreapp.tenancy import get_current_empresa
import math


class MisServiciosView(LoginRequiredMixin, ListView):
    model = Servicio
    template_name = "servicios/mis_servicios.html"
    context_object_name = "object_list"

    def get_queryset(self):
        qs = super().get_queryset().select_related('ruta','cliente','ruta__conductor')
        from acarreapp.tenancy import get_current_empresa
        emp = get_current_empresa()
        qs = qs.filter(ruta__empresa=emp)
        user = self.request.user
        role = getattr(getattr(user, 'userprofile', None), 'rol', '')
        if role == 'CONDUCTOR' and not user.is_staff and not user.is_superuser:
            qs = qs.filter(ruta__conductor=user)
        return qs.order_by('-id')


def _is_gerente(u):
    role = getattr(getattr(u, 'userprofile', None), 'rol', '')
    return u.is_superuser or u.is_staff or role == 'GERENTE'

@login_required
@user_passes_test(_is_gerente)
def crear_servicio(request):
    ruta_prefill = None
    initial = {}

    ruta_id = request.GET.get('ruta')
    if ruta_id:
        ruta_prefill = get_object_or_404(Ruta, pk=ruta_id)
        if ruta_prefill.estado != 'ACTIVA':
            messages.error(request, 'Esta ruta está CERRADA. No se pueden agregar servicios.')
            # Llévalo a la hoja o a la lista operativa, como prefieras:
            return redirect('rutas:hoja', pk=ruta_prefill.pk)
        initial['ruta'] = ruta_prefill.pk

    if request.method == 'POST':
        form = ServicioForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Servicio #{obj.id} creado.")
            return redirect('servicios:detail', pk=obj.pk)
    else:
        form = ServicioForm(initial=initial)

    return render(request, 'servicios/crear_servicio.html', {
        'form': form,
        'ruta_prefill': ruta_prefill
    })

@login_required
def pago_efectivo_conductor(request, pk):
    servicio = get_object_or_404(Servicio.objects.select_related('ruta','ruta__empresa','cliente'), pk=pk)
    user = request.user
    # Conductor dueño de la ruta o gerente
    role_ok = _is_gerente(user) or (servicio.ruta.conductor_id == user.id)
    if not role_ok:
        return HttpResponseForbidden('No autorizado')

    if servicio.ruta.estado != 'ACTIVA':
        messages.error(request, 'La ruta está cerrada.')
        return redirect('servicios:detail', pk=servicio.pk)

    if request.method == 'POST':
        try:
            monto = int(request.POST.get('monto') or '0')
        except ValueError:
            monto = 0

        saldo = max(servicio.valor - servicio.anticipo, 0)
        if monto <= 0:
            messages.error(request, 'Ingresa un valor positivo.')
        elif saldo <= 0:
            messages.info(request, 'Este servicio ya está pagado.')
        else:
            abono = min(monto, saldo)
            servicio.anticipo += abono
            servicio.estado_pago = Servicio.PAGADO if servicio.anticipo >= servicio.valor else Servicio.ANTICIPO
            servicio.save(update_fields=['anticipo','estado_pago'])

            # ---- concepto PRO ----
            cliente_nombre = getattr(getattr(servicio, 'cliente', None), 'nombre', None)
            if not cliente_nombre:
                # fallback a str(cliente) o texto por defecto
                cliente_obj = getattr(servicio, 'cliente', None)
                cliente_nombre = str(cliente_obj) if cliente_obj else "Cliente sin nombre"

            origen  = getattr(servicio, 'origen', None)
            destino = getattr(servicio, 'destino', None)
            trayecto = f" ({origen or '—'} → {destino or '—'})" if (origen or destino) else ""

            concepto_text = f"Pago servicio – {cliente_nombre}{trayecto}"

            # Si el modelo MovimientoCaja tiene FK a servicio, la enviamos.
            extra = {}
            try:
                # detecta si existe campo 'servicio'
                if any(f.name == 'servicio' for f in MovimientoCaja._meta.get_fields()):
                    extra['servicio'] = servicio
            except Exception:
                pass

            MovimientoCaja.objects.create(
                empresa=servicio.ruta.empresa,
                ruta=servicio.ruta,
                tipo='INGRESO',
                concepto=concepto_text,
                valor=abono,
                usuario=user,
                **extra
            )

            if monto > saldo:
                messages.warning(request, f'El valor superaba el saldo; se registraron ${abono:,}.')
            else:
                messages.success(request, f'Abono de ${abono:,} registrado en caja.')

    return redirect('servicios:detail', pk=servicio.pk)


@login_required
@user_passes_test(_is_gerente)
def editar_servicio(request, pk):
    obj = get_object_or_404(Servicio, pk=pk)
    if obj.ruta and obj.ruta.estado != 'ACTIVA':
        messages.error(request, 'No puedes editar servicios de una ruta CERRADA.')
        return redirect('servicios:detail', pk=obj.pk)
    else:
        form = ServicioForm(instance=obj)
    return render(request, 'servicios/crear_servicio.html', {'form': form, 'ruta_prefill': obj.ruta})

@login_required
@user_passes_test(_is_gerente)
def eliminar_servicio(request, pk):
    obj = get_object_or_404(Servicio, pk=pk)
    ruta_pk = obj.ruta_id
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Servicio eliminado.')
        return redirect('rutas:detail', pk=ruta_pk)
    return render(request, 'servicios/confirmar_eliminar.html', {'obj': obj})


class ServicioDetailView(LoginRequiredMixin, DetailView):
    model = Servicio
    template_name = "servicios/detail.html"
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        s: Servicio = ctx['object']

        user = self.request.user
        es_gerente = user.is_superuser or user.is_staff or getattr(getattr(user,'userprofile',None),'rol','')=='GERENTE'
        es_conductor = (getattr(s.ruta, 'conductor_id', None) == user.id)

        # --- métricas tiempo ---
        duracion = None
        if s.recogido_en and s.entregado_en and s.entregado_en >= s.recogido_en:
            duracion = timesince(s.entregado_en, s.recogido_en)  # ej. “3 hours, 12 minutes”

        # --- distancia (Haversine) ---
        distancia_km = None
        if all([s.lat_recogida, s.lon_recogida, s.lat_entrega, s.lon_entrega]):
            R = 6371.0
            φ1 = math.radians(s.lat_recogida);  λ1 = math.radians(s.lon_recogida)
            φ2 = math.radians(s.lat_entrega);   λ2 = math.radians(s.lon_entrega)
            dφ = φ2 - φ1; dλ = λ2 - λ1
            a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
            c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
            distancia_km = round(R*c, 2)  # km aprox. línea recta

        # --- URLs de ruta para Google Maps (si hay coordenadas) ---
        directions_url = None
        if all([s.lat_recogida, s.lon_recogida, s.lat_entrega, s.lon_entrega]):
            directions_url = (
                f"https://www.google.com/maps/dir/?api=1"
                f"&origin={s.lat_recogida},{s.lon_recogida}"
                f"&destination={s.lat_entrega},{s.lon_entrega}"
            )

        ctx.update({
            'es_gerente': es_gerente,
            'puede_marcar_recogido': es_conductor and not s.recogido,
            'puede_marcar_entregado': es_conductor and s.recogido and not s.entregado,
            'puede_registrar_efectivo': es_conductor and (s.estado_pago != Servicio.PAGADO),

            'max_pago': s.saldo_cartera,       # tope para el input number
            'duracion': duracion,               # texto human-readable
            'distancia_km': distancia_km,       # float o None
            'directions_url': directions_url,   # str o None
        })
        return ctx





@login_required
def marcar_recogido(request, pk):
    s = get_object_or_404(Servicio.objects.select_related('ruta','ruta__conductor'), pk=pk)
    user = request.user
    if s.ruta.estado != 'ACTIVA':
        messages.error(request, 'La ruta está cerrada.')
        return redirect('servicios:detail', pk=pk)
    es_gerente = user.is_superuser or user.is_staff or getattr(getattr(user,'userprofile',None),'rol','')=='GERENTE'
    es_duenio  = (s.ruta.conductor_id == user.id)
    if not (es_gerente or es_duenio):
        return HttpResponseForbidden('No autorizado')

    if request.method == 'POST':
        s.marcar_recogido(request.POST.get('lat'), request.POST.get('lon'))
        s.save(update_fields=['recogido','recogido_en','lat_recogida','lon_recogida'])
        messages.success(request, 'Servicio marcado como recogido.')
    return redirect('servicios:detail', pk=pk)

@login_required
def marcar_entregado(request, pk):
    s = get_object_or_404(Servicio.objects.select_related('ruta','ruta__conductor'), pk=pk)
    user = request.user
    if s.ruta.estado != 'ACTIVA':
        messages.error(request, 'La ruta está cerrada.')
        return redirect('servicios:detail', pk=pk)
    es_gerente = user.is_superuser or user.is_staff or getattr(getattr(user,'userprofile',None),'rol','')=='GERENTE'
    es_duenio  = (s.ruta.conductor_id == user.id)
    if not (es_gerente or es_duenio):
        return HttpResponseForbidden('No autorizado')

    if request.method == 'POST':
        s.marcar_entregado(request.POST.get('lat'), request.POST.get('lon'))
        s.save(update_fields=['entregado','entregado_en','lat_entrega','lon_entrega'])
        messages.success(request, 'Servicio marcado como entregado.')
    return redirect('servicios:detail', pk=pk)



def marcar_pagado_gerente(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    servicio.estado_pago = Servicio.PAGADO
    servicio.anticipo = servicio.valor
    servicio.save(update_fields=['estado_pago', 'anticipo'])
    messages.success(request, f"Servicio #{servicio.id} marcado como pagado (sin afectar caja).")
    return redirect('servicios:detail', pk=servicio.pk)


@login_required
def comentar_servicio(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == 'POST':
        form = ServicioComentarioForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.servicio = servicio
            c.autor = request.user
            c.save()
            messages.success(request, "Comentario agregado.")
        else:
            messages.error(request, "No se pudo agregar el comentario.")
    return redirect('servicios:detail', pk=servicio.pk)

class ServiciosPorRutaView(ListView):
    model = Servicio
    template_name = 'servicios/list_por_ruta.html'
    context_object_name = 'servicios'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        emp = get_current_empresa()
        self.ruta = get_object_or_404(
            Ruta.objects.select_related('conductor','vehiculo'),
            pk=kwargs['ruta_id'], empresa=emp
        )
        role = getattr(getattr(request.user, 'userprofile', None), 'rol', '')
        if role == 'CONDUCTOR' and not (request.user.is_staff or request.user.is_superuser):
            if self.ruta.conductor_id != request.user.id:
                messages.error(request, 'No autorizado para ver esta ruta.')
                from django.shortcuts import redirect
                return redirect('rutas:list')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Servicio.objects.filter(
            ruta=self.ruta
        ).select_related('cliente','ruta')

        # 👇 CAMBIA ESTO:
        return qs.order_by('orden', 'id')
        # (antes estaba: return qs.order_by('entregado', 'id'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        role = getattr(getattr(user, 'userprofile', None), 'rol', '')
        ctx.update({
            'ruta': self.ruta,
            'es_conductor': role == 'CONDUCTOR',
            'es_gerente': user.is_superuser or user.is_staff or role == 'GERENTE',
        })
        return ctx


class MisServiciosListView(LoginRequiredMixin, ListView):
    model = Servicio
    template_name = "servicios/mis_servicios.html"  # o "servicios/mis.html" si prefieres
    context_object_name = "object_list"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('ruta','cliente','ruta__conductor')
        emp = get_current_empresa()
        qs = qs.filter(ruta__empresa=emp)

        user = self.request.user
        role = getattr(getattr(user, 'userprofile', None), 'rol', '')
        if role == 'CONDUCTOR' and not user.is_staff and not user.is_superuser:
            qs = qs.filter(ruta__conductor=user)

        GET = self.request.GET
        if GET.get("solo_no_entregados") == "1":
            if hasattr(Servicio, "entregado"):
                qs = qs.filter(entregado=False)
            else:
                qs = qs.filter(entregado_en__isnull=True)

        if GET.get("solo_rutas_activas") == "1":
            if hasattr(Ruta, "estado"):
                qs = qs.filter(ruta__estado="ACTIVA")
            elif hasattr(Ruta, "cerrada"):
                qs = qs.filter(ruta__cerrada=False)

        if GET.get("activos") == "1":
            if hasattr(Servicio, "entregado"):
                qs = qs.filter(entregado=False)
            else:
                qs = qs.filter(entregado_en__isnull=True)

        return qs.order_by('-id')


from rutas.views import is_gerente, is_conductor

@login_required
def list_por_ruta(request, ruta_id: int):
    ruta = get_object_or_404(Ruta, pk=ruta_id)

    # 👇 CLAVE: mostrar en el orden guardado
    servicios = (Servicio.objects
                 .select_related('cliente')
                 .filter(ruta=ruta)
                 .order_by('orden', 'id'))

    return render(request, "servicios/list_por_ruta.html", {
        "ruta": ruta,
        "servicios": servicios,
        "es_gerente": is_gerente(request.user),
        "es_conductor": is_conductor(request.user),
    })