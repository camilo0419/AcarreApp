# servicios/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView
from django.utils import timezone
from django.http import HttpResponseForbidden
from .forms import ServicioForm, ServicioComentarioForm
from .models import Servicio, ServicioComentario
from rutas.models import Ruta, MovimientoCaja
from acarreapp.tenancy import get_current_empresa


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
    servicio = get_object_or_404(Servicio.objects.select_related('ruta','ruta__empresa'), pk=pk)
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
            MovimientoCaja.objects.create(
                empresa=servicio.ruta.empresa, ruta=servicio.ruta, tipo='INGRESO',
                concepto=f'Pago servicio #{servicio.pk}', valor=abono, usuario=user
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

        ctx['es_gerente'] = es_gerente
        ctx['puede_marcar_recogido'] = es_conductor and not s.recogido
        # 👉 entregar solo si ya está recogido y aún no se ha entregado
        ctx['puede_marcar_entregado'] = es_conductor and s.recogido and not s.entregado
        ctx['puede_registrar_efectivo'] = es_conductor and (s.estado_pago != Servicio.PAGADO)
        return ctx





def marcar_recogido(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == 'POST':
        lat = request.POST.get('lat')
        lon = request.POST.get('lon')
        servicio.marcar_recogido(lat=lat, lon=lon)
        servicio.save()
        messages.success(request, 'Servicio marcado como recogido.')
    return redirect('servicios:detail', pk=pk)

def marcar_entregado(request, pk):
    servicio = get_object_or_404(Servicio, pk=pk)
    if request.method == 'POST':
        lat = request.POST.get('lat')
        lon = request.POST.get('lon')
        servicio.marcar_entregado(lat=lat, lon=lon)
        servicio.save()
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
        self.ruta = get_object_or_404(Ruta.objects.select_related('conductor','vehiculo'), pk=kwargs['ruta_id'], empresa=emp)
        # Conductor solo su propia ruta ACTIVA
        role = getattr(getattr(request.user, 'userprofile', None), 'rol', '')
        if role == 'CONDUCTOR' and not (request.user.is_staff or request.user.is_superuser):
            if self.ruta.conductor_id != request.user.id:
                messages.error(request, 'No autorizado para ver esta ruta.')
                from django.shortcuts import redirect
                return redirect('rutas:list')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Servicio.objects.filter(ruta=self.ruta).select_related('cliente','ruta')
        # Orden que tenías “antes”: primero los no entregados, luego por id asc (o fecha), ajusta si quieres:
        return qs.order_by('entregado', 'id')
    
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