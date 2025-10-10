from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView

from acarreapp.tenancy import get_current_empresa
from .models import Ruta, MovimientoCaja, CierreRuta
import csv
from django.http import HttpResponse
from .forms import RutaForm
from .services import cerrar_ruta

# === helpers de rol ===
def is_gerente(user):
    role = getattr(getattr(user, 'userprofile', None), 'rol', '')
    return user.is_superuser or user.is_staff or role == 'GERENTE'

def is_conductor(user):
    role = getattr(getattr(user, 'userprofile', None), 'rol', '')
    return role == 'CONDUCTOR' or user.groups.filter(name__iexact='Conductor').exists()

# ===== Listado =====
@method_decorator(login_required, name='dispatch')
class RutasListView(ListView):
    model = Ruta
    template_name = 'rutas/list.html'
    context_object_name = 'rutas'
    paginate_by = 25

    def get_queryset(self):
        emp = get_current_empresa()
        qs = Ruta.objects.filter(empresa=emp).select_related('vehiculo', 'conductor')
        if is_conductor(self.request.user):
            qs = qs.filter(conductor=self.request.user, estado='ACTIVA')
        return qs.order_by('-created_at')

# ===== Hoja de ruta (detalle) =====
@method_decorator(login_required, name='dispatch')
class RutaDetailView(DetailView):
    model = Ruta
    template_name = 'rutas/detail.html'
    context_object_name = 'ruta'

    def get_queryset(self):
        emp = get_current_empresa()
        qs = Ruta.objects.filter(empresa=emp).select_related('vehiculo', 'conductor')
        if is_conductor(self.request.user):
            qs = qs.filter(conductor=self.request.user)
        return qs

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Conductor no puede ver rutas cerradas
        if is_conductor(request.user) and self.object.estado != 'ACTIVA':
            messages.warning(request, 'Esta ruta ya fue cerrada.')
            return redirect('rutas:list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ruta = self.object
        servicios = ruta.servicios.all().select_related('cliente')

        tot_servicios = servicios.count()
        valor_total = sum(s.valor for s in servicios)
        total_cobrado = sum(s.valor for s in servicios if s.estado_pago == 'PAG')
        total_pendiente = sum(getattr(s, 'saldo_cartera', 0) for s in servicios)

        movs = ruta.movimientos.all().order_by('-timestamp')
        total_gastos = sum(m.valor for m in movs if m.tipo == 'GASTO')
        total_ingresos = ruta.base_efectivo + sum(m.valor for m in movs if m.tipo == 'INGRESO')
        disponible = total_ingresos - total_gastos
        utilidad_neta = total_cobrado - total_gastos  # cobrado menos gastos

        ctx.update({
            'servicios': servicios,
            'movimientos': movs,
            'tot_servicios': tot_servicios,
            'valor_total': valor_total,
            'total_cobrado': total_cobrado,
            'total_pendiente': total_pendiente,
            'total_gastos': total_gastos,
            'total_ingresos': total_ingresos,
            'disponible': disponible,
            'utilidad_neta': utilidad_neta,
            'es_gerente': is_gerente(self.request.user),
            'es_conductor': is_conductor(self.request.user),
            'add_servicio_url': reverse('servicios:crear') + f'?ruta={ruta.pk}',
        })
        return ctx

# ===== Crear / Borrar / Cerrar =====
@login_required
@user_passes_test(is_gerente)
def crear_ruta(request):
    if request.method == 'POST':
        form = RutaForm(request.POST)
        if form.is_valid():
            ruta = form.save()
            messages.success(request, f'Ruta #{ruta.pk} creada.')
            return redirect('servicios:por_ruta', pk=ruta.pk)  # 👈 AQUÍ EL CAMBIO
    else:
        form = RutaForm()
    return render(request, 'rutas/crear_ruta.html', {'form': form})

@login_required
@user_passes_test(is_gerente)
def borrar_ruta(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk, empresa=get_current_empresa())
    if ruta.estado != 'ACTIVA':
        messages.error(request, 'No puedes borrar una ruta cerrada.')
        return redirect('rutas:hoja', pk=ruta.pk)  # hoja, no detail
    ruta.delete()
    messages.success(request, 'Ruta eliminada.')
    return redirect('rutas:list')


@login_required
def cerrar_ruta_view(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk, empresa=get_current_empresa())
    user = request.user

    if is_conductor(user):
        if ruta.conductor_id != user.id or ruta.estado != 'ACTIVA':
            return HttpResponseForbidden('No autorizado')
    elif not is_gerente(user):
        return HttpResponseForbidden('No autorizado')

    cierre = cerrar_ruta(ruta, user)

    # Mensaje
    from django.contrib import messages
    messages.success(request, f'Ruta #{ruta.pk} cerrada.')

    # Redirecciones:
    # - Conductor: ya no puede ver la ruta -> llévalo a "Mis servicios"
    # - Gerente: puede ver la hoja de ruta cerrada
    if is_conductor(user):
        return redirect('servicios:mis')
    else:
        return redirect('rutas:hoja', pk=ruta.pk)

# ===== Movimientos de caja =====
@login_required
def agregar_gasto(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk, empresa=get_current_empresa())
    if is_conductor(request.user):
        if ruta.conductor_id != request.user.id or ruta.estado != 'ACTIVA':
            return HttpResponseForbidden('No autorizado')
    if request.method == 'POST':
        concepto = (request.POST.get('concepto') or '').strip()
        valor = int(request.POST.get('valor') or '0')
        if valor <= 0:
            messages.error(request, 'El valor debe ser positivo.')
        else:
            MovimientoCaja.objects.create(
                empresa=ruta.empresa, ruta=ruta, tipo='GASTO',
                concepto=concepto or 'Gasto', valor=valor, usuario=request.user
            )
            messages.success(request, 'Gasto registrado.')
    return redirect('rutas:hoja', pk=ruta.id)


@login_required
def agregar_ingreso_extra(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk, empresa=get_current_empresa())
    if is_conductor(request.user):
        if ruta.conductor_id != request.user.id or ruta.estado != 'ACTIVA':
            return HttpResponseForbidden('No autorizado')
    if request.method == 'POST':
        concepto = (request.POST.get('concepto') or '').strip()
        valor = int(request.POST.get('valor') or '0')
        if valor <= 0:
            messages.error(request, 'El valor debe ser positivo.')
        else:
            MovimientoCaja.objects.create(
                empresa=ruta.empresa, ruta=ruta, tipo='INGRESO',
                concepto=concepto or 'Ingreso extra', valor=valor, usuario=request.user
            )
            messages.success(request, 'Ingreso registrado.')
    return redirect('rutas:hoja', pk=ruta.id)


@login_required
def cierre_resumen(request, ruta_id: int):
    ruta = get_object_or_404(Ruta, id=ruta_id)
    # Genera/actualiza el cierre cada vez que entras (o cámbialo a botón si prefieres)
    cierre = cerrar_ruta(ruta, request.user)
    servicios = ruta.servicios.select_related('cliente').all().order_by('id')
    contexto = {
        'ruta': ruta,
        'cierre': cierre,
        'servicios': servicios,
    }
    return render(request, 'rutas/cierre_resumen.html', contexto)

@login_required
def exportar_cierre_csv(request, ruta_id: int):
    ruta = get_object_or_404(Ruta, id=ruta_id)
    cierre = CierreRuta.objects.filter(ruta=ruta).first() or cerrar_ruta(ruta, request.user)
    servicios = ruta.servicios.select_related('cliente').all().order_by('id')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="cierre_ruta_{ruta.id}.csv"'
    writer = csv.writer(response)

    writer.writerow(["Resumen de Cierre"])
    writer.writerow(["Ruta", str(ruta)])
    writer.writerow(["Total servicios", cierre.total_servicios])
    writer.writerow(["Cobrado", cierre.total_cobrado])
    writer.writerow(["Pendiente", cierre.total_pendiente])
    writer.writerow(["Ingresos", cierre.total_ingresos])
    writer.writerow(["Gastos", cierre.total_gastos])
    writer.writerow(["Utilidad neta", cierre.utilidad_neta])
    writer.writerow([])

    writer.writerow(["Detalle de servicios"])
    writer.writerow(["ID", "Cliente", "Origen", "Destino", "Valor", "Estado pago"])
    for s in servicios:
        writer.writerow([s.id, getattr(s.cliente, "nombre", ""), s.origen, s.destino, s.valor, s.get_estado_pago_display() if hasattr(s, 'get_estado_pago_display') else s.estado_pago])

    return response
