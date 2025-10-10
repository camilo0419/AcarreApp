from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import date, datetime, time
import json
from acarreapp.tenancy import get_current_empresa
from .models import Ruta, MovimientoCaja, CierreRuta
from .forms import RutaForm
from .services import cerrar_ruta
from .logic import cerrar_ruta  # tu helper que realiza el cierre
from django.db import IntegrityError
# Para filtros del listado
from empresa.models import Vehiculo, Cliente   # ajusta si están en otra app
from servicios.models import Servicio          # idem

import csv


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
        qs = (Ruta.objects
              .filter(empresa=emp)
              .select_related('vehiculo', 'conductor'))

        # Conductor: solo sus rutas activas (como pediste)
        if is_conductor(self.request.user):
            qs = qs.filter(conductor=self.request.user, estado='ACTIVA')

        GET = self.request.GET

        # ---- Rango de fechas (YYYY-MM-DD) ----
        desde = (GET.get('desde') or '').strip() or None
        hasta = (GET.get('hasta') or '').strip() or None
        if desde:
            qs = qs.filter(fecha_salida__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha_salida__date__lte=hasta)

        # ---- Multi-select de vehículos (ids) ----
        vehiculos_ids = [v for v in GET.getlist('vehiculos') if v]
        if vehiculos_ids:
            qs = qs.filter(vehiculo_id__in=vehiculos_ids)

        # ---- Multi-select de clientes (ids) a través de servicios ----
        clientes_ids = [c for c in GET.getlist('clientes') if c]
        if clientes_ids:
            # related_name = 'servicios'
            qs = qs.filter(servicios__cliente_id__in=clientes_ids)

        # ---- Buscador global ----
        # --- Buscador global ---
        q = (GET.get('q') or '').strip()
        if q:
            # Campos existentes
            base = (
                Q(nombre__icontains=q) |
                Q(vehiculo__placa__icontains=q) |          # ← dejamos solo placa
                Q(conductor__username__icontains=q) |
                Q(conductor__first_name__icontains=q) |
                Q(conductor__last_name__icontains=q) |
                Q(estado__icontains=q)
            )
            if q.isdigit():
                base |= Q(id=int(q))

            # A través de servicios
            qs = qs.filter(
                base |
                Q(servicios__cliente__nombre__icontains=q) |
                Q(servicios__origen__icontains=q) |
                Q(servicios__destino__icontains=q)
            )

        # Evita duplicados por joins con servicios
        return qs.distinct().order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = get_current_empresa()

        # Para poblar selects
        ctx['vehiculos'] = Vehiculo.objects.filter(empresa=emp).order_by('placa')
        ctx['clientes']  = Cliente.objects.filter(empresa=emp).order_by('nombre')

        # ❗ Lo que antes intentabas en el template:
        ctx['selected_vehiculos'] = self.request.GET.getlist('vehiculos')
        ctx['selected_clientes']  = self.request.GET.getlist('clientes')

        # Para paginación conservando filtros (q, fechas, vehiculos, clientes)
        params = self.request.GET.copy()
        if 'page' in params:
            try:
                del params['page']
            except KeyError:
                pass
        ctx['qs_no_page'] = ('&' + params.urlencode()) if params else ''

        # Flags de rol (si quieres condicionar UI)
        ctx['es_gerente'] = is_gerente(self.request.user)
        ctx['es_conductor'] = is_conductor(self.request.user)
        return ctx


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
        utilidad_neta = total_cobrado - total_gastos

        # 👉 nuevo: ingresos sin base
        base = ruta.base_efectivo or 0
        ingresos_sin_base = (total_ingresos or 0) - base

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
            'ingresos_sin_base': ingresos_sin_base,   # ← aquí
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
            return redirect('servicios:por_ruta', ruta_id=ruta.pk)
    else:
        form = RutaForm()
    return render(request, 'rutas/crear_ruta.html', {'form': form})


@login_required
@user_passes_test(is_gerente)
def borrar_ruta(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk, empresa=get_current_empresa())
    if ruta.estado != 'ACTIVA':
        messages.error(request, 'No puedes borrar una ruta cerrada.')
        return redirect('rutas:hoja', pk=ruta.pk)
    ruta.delete()
    messages.success(request, 'Ruta eliminada.')
    return redirect('rutas:list')


@login_required
def cerrar_ruta_view(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk)

    # ... tus permisos aquí ...

    if request.method != 'POST':
        messages.info(request, 'Confirma el cierre desde la Hoja de ruta.')
        return redirect('rutas:hoja', pk=ruta.pk)

    # ... validación de servicios pendientes ...

    try:
        cierre = cerrar_ruta(ruta, request.user)
    except ValueError as e:
        messages.error(request, f"No se pudo cerrar la ruta: {e}")
        return redirect('rutas:hoja', pk=ruta.pk)
    except IntegrityError:
        messages.error(request, "No se pudo cerrar la ruta (integridad de datos).")
        return redirect('rutas:hoja', pk=ruta.pk)

    messages.success(request, f'Ruta #{ruta.pk} cerrada.')
    return redirect('rutas:cierre_resumen', ruta_id=ruta.pk)


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


# rutas/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import Ruta
from .logic import cerrar_ruta  # ya existente

@login_required
def cierre_resumen(request, ruta_id: int):
    ruta = get_object_or_404(Ruta, id=ruta_id)
    cierre = cerrar_ruta(ruta, request.user)

    servicios = (
        ruta.servicios.select_related('cliente')
        .all().order_by('id')
    )

    # Ventas
    total_venta = sum((s.valor or 0) for s in servicios)

    # Cobros
    total_cobrado = cierre.total_cobrado or 0
    pendiente_cobro = max(total_venta - total_cobrado, 0)

    # Caja
    base_efectivo   = ruta.base_efectivo or 0
    total_ingresos  = cierre.total_ingresos or 0   # puede o no traer la base incluida
    total_gastos    = cierre.total_gastos or 0

    # Quita la base si viene incluida; si no hay dato fiable, usa lo cobrado
    ingresos_en_ruta_calc = total_ingresos - base_efectivo
    if ingresos_en_ruta_calc > 0:
        ingresos_en_ruta_final = ingresos_en_ruta_calc
    else:
        ingresos_en_ruta_final = total_cobrado  # fallback consistente con lo que ves en UI

    # Efectivo a entregar (CONSISTENTE con lo mostrado)
    efectivo_entregar = base_efectivo + ingresos_en_ruta_final - total_gastos

    # Utilidad operativa
    utilidad_operativa = total_venta - total_gastos

    context = {
        'ruta': ruta,
        'cierre': cierre,
        'servicios': servicios,

        'total_venta': total_venta,
        'total_cobrado': total_cobrado,
        'pendiente_cobro': pendiente_cobro,

        'base_efectivo': base_efectivo,
        'ingresos_en_ruta': ingresos_en_ruta_final,  # << usa SIEMPRE este
        'total_gastos': total_gastos,
        'efectivo_entregar': efectivo_entregar,
        'utilidad_operativa': utilidad_operativa,
    }
    return render(request, 'rutas/cierre_resumen.html', context)



@login_required
def recorrido_ruta_view(request, ruta_id: int):
    """Muestra un mapa (Leaflet) con el recorrido aproximado:
       puntos de recogida/entrega ordenados por timestamp, unidos por polilínea."""
    ruta = get_object_or_404(Ruta, id=ruta_id)

    servicios = (
        ruta.servicios
        .all()
        .order_by('id')
    )

    puntos = []
    for s in servicios:
        if s.recogido_en and s.lat_recogida and s.lon_recogida:
            puntos.append({
                "ts": s.recogido_en.isoformat(),
                "lat": float(s.lat_recogida),
                "lon": float(s.lon_recogida),
                "tipo": "recogida",
                "label": f"Recogida — Serv #{s.id}",
            })
        if s.entregado_en and s.lat_entrega and s.lon_entrega:
            puntos.append({
                "ts": s.entregado_en.isoformat(),
                "lat": float(s.lat_entrega),
                "lon": float(s.lon_entrega),
                "tipo": "entrega",
                "label": f"Entrega — Serv #{s.id}",
            })

    puntos.sort(key=lambda p: p["ts"])
    puntos_json = mark_safe(json.dumps(puntos))  # seguro para insertar en JS

    return render(request, 'rutas/recorrido.html', {
        'ruta': ruta,
        'puntos_json': puntos_json,
    })


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
        writer.writerow([
            s.id,
            getattr(s.cliente, "nombre", ""),
            s.origen,
            s.destino,
            s.valor,
            s.get_estado_pago_display() if hasattr(s, 'get_estado_pago_display') else s.estado_pago
        ])

    return response


# === EXCEL EXPORT (openpyxl) ===
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from django.utils import timezone
from datetime import date, datetime, time
from decimal import Decimal

# ----------------- helpers -----------------
def xls(v):
    """
    Normaliza valores a tipos aceptados por openpyxl.
    - Convierte Decimal -> float
    - Convierte datetime/time aware -> naive (sin tz) en hora local
    - Cualquier objeto no soportado -> str
    """
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        if timezone.is_aware(v):
            v = timezone.localtime(v)
        return v.replace(tzinfo=None)
    if isinstance(v, time):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return v
    return str(v)

def _money_fmt(cell):
    cell.number_format = u'[$$-409] #,##0'
    return cell

def _auto_fit(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for c in col:
            v = "" if c.value is None else str(c.value)
            max_len = max(max_len, len(v))
        ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), 45)

# ----------------- view -----------------
@login_required
def exportar_cierre_xlsx(request, ruta_id: int):
    ruta = get_object_or_404(Ruta, id=ruta_id)
    cierre = CierreRuta.objects.filter(ruta=ruta).first() or cerrar_ruta(ruta, request.user)
    servicios = ruta.servicios.select_related('cliente').all().order_by('id')

    # ===== métricas (coherentes con la vista) =====
    total_venta = sum((s.valor or 0) for s in servicios)
    total_cobrado = cierre.total_cobrado or 0
    pendiente_cobro = max(total_venta - total_cobrado, 0)

    base_efectivo  = ruta.base_efectivo or 0
    total_ingresos = cierre.total_ingresos or 0
    total_gastos   = cierre.total_gastos or 0

    # Ingresos en ruta (quita base; si no hay dato fiable, usa cobrado)
    ingresos_en_ruta_calc = total_ingresos - base_efectivo
    ingresos_en_ruta = ingresos_en_ruta_calc if ingresos_en_ruta_calc > 0 else total_cobrado

    # Efectivo a entregar (lo mismo que muestras en UI)
    efectivo_entregar = base_efectivo + ingresos_en_ruta - total_gastos

    utilidad_operativa = total_venta - total_gastos

    # ===== estilos =====
    COLOR_PRIMARY = "1F2A5A"
    COLOR_LINE    = "E6E8F0"
    COLOR_OK      = "236A3B"
    COLOR_WARN    = "8A1A1A"
    header_fill   = PatternFill("solid", fgColor=COLOR_PRIMARY)
    header_font   = Font(color="FFFFFF", bold=True)
    subhead_font  = Font(color=COLOR_PRIMARY, bold=True)
    bold          = Font(bold=True)
    center        = Alignment(horizontal="center", vertical="center")
    right         = Alignment(horizontal="right",  vertical="center")
    thin_border   = Border(left=Side(style="thin", color=COLOR_LINE),
                           right=Side(style="thin", color=COLOR_LINE),
                           top=Side(style="thin", color=COLOR_LINE),
                           bottom=Side(style="thin", color=COLOR_LINE))

    wb = Workbook()

    # ===== Hoja 1: Resumen =====
    ws = wb.active
    ws.title = "Resumen"

    ws.merge_cells("A1:F1")
    ws["A1"] = f"Cierre de ruta — {ruta.nombre or '(sin nombre)'}  #{ruta.id}"
    ws["A1"].fill = header_fill
    ws["A1"].font = Font(color="FFFFFF", bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws["A3"] = "Estado";     ws["B3"] = xls((ruta.estado or "").title())
    ws["A4"] = "Vehículo";   ws["B4"] = xls(getattr(ruta.vehiculo, "placa", ruta.vehiculo))
    ws["A5"] = "Conductor";  ws["B5"] = xls(getattr(ruta.conductor, "username", ruta.conductor))
    ws["A6"] = "Salida";     ws["B6"] = xls(ruta.fecha_salida)
    ws["B6"].number_format = "yyyy-mm-dd hh:mm"
    for r in range(3, 7):
        ws[f"A{r}"].font = bold

    ws["D3"] = "Valor total de servicios (venta)"; ws["E3"] = xls(total_venta);        _money_fmt(ws["E3"])
    ws["D4"] = "Cobrado (total)";                  ws["E4"] = xls(total_cobrado);      _money_fmt(ws["E4"])
    ws["D5"] = "Pendiente por cobrar";             ws["E5"] = xls(pendiente_cobro);    _money_fmt(ws["E5"])
    ws["D6"] = "Utilidad operativa";               ws["E6"] = xls(utilidad_operativa); _money_fmt(ws["E6"])
    for cell in ("D3","D4","D5","D6"):
        ws[cell].font = subhead_font

    ws["A8"] = "Caja de ruta"; ws["A8"].font = subhead_font
    ws.append(["", "Base",               xls(base_efectivo)]);       _money_fmt(ws.cell(row=9,  column=3))
    ws.append(["", "Ingresos en ruta",   xls(ingresos_en_ruta)]);    _money_fmt(ws.cell(row=10, column=3))
    ws.append(["", "Gastos",             xls(-abs(total_gastos))]);  _money_fmt(ws.cell(row=11, column=3))
    ws.append(["", "Efectivo a entregar",xls(efectivo_entregar)]);   _money_fmt(ws.cell(row=12, column=3))

    for r in range(9, 13):
        for c in range(2, 3+1):
            ws.cell(row=r, column=c).border = thin_border
            if c == 2: ws.cell(row=r, column=c).font = bold
            if c == 3: ws.cell(row=r, column=c).alignment = right

    ws["C9"].font  = Font(color=COLOR_OK, bold=True)
    ws["C10"].font = Font(color=COLOR_OK, bold=True)
    ws["C11"].font = Font(color=COLOR_WARN, bold=True)
    ws["C12"].font = Font(bold=True)

    _auto_fit(ws)

    # ===== Hoja 2: Servicios =====
    ws2 = wb.create_sheet("Servicios")
    headers = ["ID", "Cliente", "Origen", "Destino", "Valor", "Estado pago", "Recogido", "Entregado"]
    ws2.append(headers)
    for i, h in enumerate(headers, start=1):
        cell = ws2.cell(row=1, column=i, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = thin_border

    for s in servicios:
        row = [
            xls(s.id),
            xls(getattr(getattr(s, "cliente", None), "nombre", getattr(s, "cliente", "—"))),
            xls(s.origen or "—"),
            xls(s.destino or "—"),
            xls(s.valor or 0),
            xls(s.get_estado_pago_display() if hasattr(s, "get_estado_pago_display") else s.estado_pago),
            xls(getattr(s, "recogido_en", None)),
            xls(getattr(s, "entregado_en", None)),
        ]
        ws2.append(row)

    # formatos
    for r in range(2, ws2.max_row + 1):
        _money_fmt(ws2.cell(row=r, column=5)).alignment = right
        ws2.cell(row=r, column=7).number_format = "yyyy-mm-dd hh:mm"
        ws2.cell(row=r, column=8).number_format = "yyyy-mm-dd hh:mm"

    for r in range(1, ws2.max_row + 1):
        for c in range(1, ws2.max_column + 1):
            ws2.cell(row=r, column=c).border = thin_border

    ws2.freeze_panes = "A2"
    ws2.auto_filter.ref = f"A1:{get_column_letter(ws2.max_column)}1"
    _auto_fit(ws2)

    # ===== Hoja 3: Notas =====
    ws3 = wb.create_sheet("Notas")
    ws3["A1"] = "Generado por"; ws3["B1"] = xls(request.user.get_username())
    ws3["A2"] = "Fecha cierre"; ws3["B2"] = xls(getattr(cierre, "updated_at", None) or getattr(cierre, "created_at", None))
    ws3["A3"] = "Empresa";     ws3["B3"] = xls(getattr(ruta.empresa, "nombre", str(ruta.empresa)))
    ws3["B2"].number_format = "yyyy-mm-dd hh:mm"
    ws3["A1"].font = Font(bold=True); ws3["A2"].font = Font(bold=True); ws3["A3"].font = Font(bold=True)
    _auto_fit(ws3)

    # respuesta
    filename = f"cierre_ruta_{ruta.id}.xlsx"
    resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(resp)
    return resp