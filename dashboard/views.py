# dashboard/views.py
from datetime import date, timedelta
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import models
from django.db.models import (
    Sum, Count, F, Case, When, Value, IntegerField, FloatField, DateField,
    ExpressionWrapper
)
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse, Http404
from django.utils.timezone import localdate
from django.views import View
from django.views.generic import TemplateView

from acarreapp.tenancy import get_current_empresa
from servicios.models import Servicio
from rutas.models import Ruta


# -------- permisos ----------
class GerenteRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_denied_message = "No tienes permisos para ver esta página."
    def test_func(self):
        u = self.request.user
        rol = getattr(getattr(u, "userprofile", None), "rol", "") or ""
        return u.is_superuser or u.is_staff or rol == "GERENTE"


# -------- helpers comunes ----------
def _empresa_serv_qs():
    emp = get_current_empresa()
    qs = Servicio.objects.select_related("ruta", "cliente", "ruta__conductor")
    return qs.filter(ruta__empresa=emp) if emp else qs.none()

def _rutas_qs_base():
    qs = Ruta.objects.select_related("vehiculo", "conductor")
    emp = get_current_empresa()
    if emp:
        qs = qs.filter(empresa=emp)
    return qs

def _rutas_activas_qs():
    qs = _rutas_qs_base()
    if hasattr(Ruta, "estado"):
        qs = qs.filter(estado="ACTIVA")
    elif hasattr(Ruta, "cerrada"):
        qs = qs.filter(cerrada=False)
    return qs

def _rutas_activas_count():
    return _rutas_activas_qs().count()

def _filter_day(qs, path, model, field_name, day):
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return qs
    if isinstance(field, models.DateTimeField):
        return qs.filter(**{f"{path}__date": day})
    return qs.filter(**{path: day})

def _servicios_no_entregados(qs):
    # Boolean 'entregado' y/o timestamp 'entregado_en'
    if hasattr(Servicio, "entregado"):
        return qs.filter(entregado=False)
    return qs.filter(entregado_en__isnull=True)

def _servicios_entregados_hoy(qs, hoy):
    if hasattr(Servicio, "entregado_en"):
        return _filter_day(qs, "entregado_en", Servicio, "entregado_en", hoy)
    return qs.none()


# ---------- NUEVO: puntos desde Servicios (recogido/entregado) ----------
def _route_points_from_servicios(ruta: Ruta):
    """
    Devuelve lista de [lat, lon] ordenada por tiempo, tomando de cada Servicio:
      (recogido_en, lat_recogida, lon_recogida) y (entregado_en, lat_entrega, lon_entrega).
    """
    eventos = []
    srv = Servicio.objects.filter(ruta=ruta).only(
        "recogido_en", "entregado_en",
        "lat_recogida", "lon_recogida",
        "lat_entrega", "lon_entrega"
    )
    for s in srv:
        if s.recogido_en and s.lat_recogida is not None and s.lon_recogida is not None:
            eventos.append((s.recogido_en, float(s.lat_recogida), float(s.lon_recogida)))
        if s.entregado_en and s.lat_entrega is not None and s.lon_entrega is not None:
            eventos.append((s.entregado_en, float(s.lat_entrega), float(s.lon_entrega)))
    eventos.sort(key=lambda x: x[0])
    return [[lat, lon] for _, lat, lon in eventos]

def _rutas_activas_cards(limit=6):
    qs = _rutas_activas_qs().annotate(servicios_total=Count("servicios"))
    qs = qs.order_by("-fecha_salida") if hasattr(Ruta, "fecha_salida") else qs.order_by("-id")
    items = []
    for r in qs[:limit]:
        placa = getattr(getattr(r, "vehiculo", None), "placa", "s/n")
        conductor = getattr(r, "conductor", None)
        nombre_conductor = ""
        if conductor:
            nombre_conductor = (
                f"{getattr(conductor,'first_name','')} {getattr(conductor,'last_name','')}".strip()
                or getattr(conductor, "username", "")
            )
        items.append({
            "id": r.id,
            "nombre": getattr(r, "nombre", f"Ruta #{r.id}"),
            "placa": placa,
            "conductor": nombre_conductor,
            "servicios_total": getattr(r, "servicios_total", 0),
        })
    return items


# -------- helpers de rango/series ----------
def _parse_rango(request):
    """
    Devuelve (desde, hasta, label) según GET: ?rango=mes|7d|30d|custom&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    """
    hoy = localdate()
    rango = (request.GET.get("rango") or "mes").lower()
    if rango == "7d":
        return hoy - timedelta(days=6), hoy, "7 días"
    if rango == "30d":
        return hoy - timedelta(days=29), hoy, "30 días"
    if rango == "custom":
        try:
            d = date.fromisoformat(request.GET.get("desde") or str(hoy.replace(day=1)))
        except Exception:
            d = hoy.replace(day=1)
        try:
            h = date.fromisoformat(request.GET.get("hasta") or str(hoy))
        except Exception:
            h = hoy
        if h < d:
            d, h = h, d
        return d, h, "Personalizado"
    # mes actual
    return hoy.replace(day=1), hoy, "Mes actual"


# --- Helper seguro para SQLite: serie diaria usando solo agregación numérica ---
def _serie_por_dia(qs, date_path="ruta__fecha_salida", value_field="valor", desde=None, hasta=None):
    """
    Devuelve (labels, series) para gráfico diario.
    Sólo usa SUM numérico agrupado por la fecha (DateField) → compatible con SQLite.
    """
    if desde is None or hasta is None:
        # intenta inferir del queryset, pero mejor pásalos desde la vista
        hoy = localdate()
        desde = hoy.replace(day=1)
        hasta = hoy

    # Agregamos por la fecha directamente (es DateField en Ruta)
    agregados = (
        qs.values(date_path)
          .annotate(total=Coalesce(Sum(value_field), 0))
    )

    # Mapeamos fecha -> total
    mapa = {row[date_path]: int(row["total"] or 0) for row in agregados if row.get(date_path)}

    # Construimos la serie continua día a día
    labels, series = [], []
    d = desde
    while d <= hasta:
        labels.append(d.strftime("%Y-%m-%d"))
        series.append(mapa.get(d, 0))
        d += timedelta(days=1)

    return labels, series


# -------- Vistas de página ----------
class DashboardHomeView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = localdate()
        primer_dia_mes = date(hoy.year, hoy.month, 1)

        serv_empresa = _empresa_serv_qs()

        serie_mes = serv_empresa.filter(ruta__fecha_salida__range=(primer_dia_mes, hoy))
        fact = serie_mes.aggregate(t=Coalesce(Sum("valor"), 0))["t"] or 0
        cob  = serie_mes.aggregate(t=Coalesce(Sum("anticipo"), 0))["t"] or 0

        servicios_activos = _servicios_no_entregados(serv_empresa).filter(
            ruta__in=_rutas_activas_qs()
        ).count()

        rutas_activas = _rutas_activas_count()
        serv_hoy_base = _filter_day(serv_empresa, "ruta__fecha_salida", Ruta, "fecha_salida", hoy)
        pendientes_hoy = _servicios_no_entregados(serv_hoy_base).count()
        entregadas_hoy = _servicios_entregados_hoy(serv_empresa, hoy).count()

        u = self.request.user
        nombre_usuario = (f"{getattr(u,'first_name','')} {getattr(u,'last_name','')}".strip()
                          or getattr(u, "username", ""))

        ctx.update({
            "hoy": hoy,
            "kpi_facturado": int(fact),
            "kpi_cobrado": int(cob),
            "kpi_cartera": int(fact) - int(cob),
            "servicios_activos": servicios_activos,
            "rutas_activas": rutas_activas,
            "pendientes_hoy": pendientes_hoy,
            "entregadas_hoy": entregadas_hoy,
            "nombre_usuario": nombre_usuario,
            "rutas_cards": _rutas_activas_cards(limit=6),
        })
        return ctx


# =========================
#     ANALÍTICA: OPERACIÓN
# =========================
class OperacionView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/operacion.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = localdate()
        desde, hasta, _label = _parse_rango(self.request)

        # Base: por empresa + rango
        base = _empresa_serv_qs().filter(ruta__fecha_salida__range=(desde, hasta))

        # Filtros opcionales del UI
        vendedor = self.request.GET.get("vendedor")
        if vendedor and vendedor.isdigit():
            base = base.filter(ruta__conductor_id=int(vendedor))

        # Si más adelante usas "punto", aplica aquí:
        # punto = self.request.GET.get("punto")
        # if punto and punto.isdigit():
        #     base = base.filter(punto_id=int(punto))

        # --- KPIs básicos (solo SUM numéricas) ---
        facturado = base.aggregate(t=Coalesce(Sum("valor"), 0))["t"] or 0
        cobrado   = base.aggregate(t=Coalesce(Sum("anticipo"), 0))["t"] or 0
        num_srv   = base.count()
        ticket_prom = int(round(facturado / num_srv, 0)) if num_srv else 0
        pct_cobrado = (cobrado / facturado * 100.0) if facturado else 0.0

        # --- Lead-time promedio (horas) en Python (evita SUM(Duration) en SQL) ---
        total_seconds = 0.0
        pares = 0
        for rg, eg in base.filter(recogido_en__isnull=False, entregado_en__isnull=False)\
                          .values_list("recogido_en", "entregado_en"):
            if rg and eg and eg > rg:
                total_seconds += (eg - rg).total_seconds()
                pares += 1
        lead_time_horas = f"{(total_seconds / pares) / 3600.0:.1f} h" if pares else "—"

        # --- Serie por día (labels y valores) ---
        xdias, ydia_facturado = _serie_por_dia(base, "ruta__fecha_salida", "valor", desde, hasta)

        # --- Ranking por conductores (top 8) ---
        por_conductor = (base
                         .values("ruta__conductor__username")
                         .annotate(total=Coalesce(Sum("valor"), 0))
                         .order_by("-total")[:8])
        cond_labels = [i["ruta__conductor__username"] or "—" for i in por_conductor]
        cond_series = [int(i["total"] or 0) for i in por_conductor]

        # --- Distribución por clientes (top 8) ---
        por_cliente = (base
                       .values("cliente__nombre")
                       .annotate(total=Coalesce(Sum("valor"), 0))
                       .order_by("-total")[:8])
        cli_labels = [i["cliente__nombre"] or "—" for i in por_cliente]
        cli_series = [int(i["total"] or 0) for i in por_cliente]

        # --- Entregadas/Pendientes HOY (usando helpers existentes) ---
        serv_empresa = _empresa_serv_qs()
        entregadas_hoy = _servicios_entregados_hoy(serv_empresa, hoy).count()
        pendientes_hoy = _servicios_no_entregados(
            _filter_day(serv_empresa, "ruta__fecha_salida", Ruta, "fecha_salida", hoy)
        ).count()

        # --- Tabla compacta (últimos 50 del rango) ---
        op_servicios = (base
                        .order_by("-ruta__fecha_salida", "-id")
                        .only("id", "valor", "estado_pago", "anticipo", "origen", "destino",
                              "cliente__nombre", "ruta__fecha_salida", "ruta__conductor__username")[:50])

        # --- Selects de filtros para el template (listas siempre seguras) ---
        filtros_clientes = (base
                            .values("cliente__id", "cliente__nombre")
                            .annotate(n=Count("id"))
                            .order_by("cliente__nombre"))
        filtros_clientes = [
            {"id": i["cliente__id"], "nombre": i["cliente__nombre"] or "—"}
            for i in filtros_clientes if i["cliente__id"]
        ]
        filtros_vendedores = (base
                              .values("ruta__conductor__id", "ruta__conductor__username")
                              .annotate(n=Count("id"))
                              .order_by("ruta__conductor__username"))
        filtros_vendedores = [
            {"id": i["ruta__conductor__id"], "username": i["ruta__conductor__username"] or "—"}
            for i in filtros_vendedores if i["ruta__conductor__id"]
        ]

        # --- Top nombre rápido (por si lo quieres en el UI) ---
        op_top_cliente = {"nombre": cli_labels[0]} if cli_labels else None
        op_top_conductor = cond_labels[0] if cond_labels else None

        # --- Contexto final ---
        ctx.update({
            "op_facturado": int(facturado),
            "op_cobrado": int(cobrado),
            "op_pct_cobrado": pct_cobrado,
            "op_num_servicios": num_srv,
            "op_ticket_prom": int(ticket_prom),
            "lead_time_horas": lead_time_horas,          # usado en tu último template
            "op_lead_time_horas": lead_time_horas,       # por compatibilidad con versiones previas

            "op_xdias": xdias,
            "op_ydia_facturado": ydia_facturado,

            "op_conductores_labels": cond_labels,
            "op_conductores_series": cond_series,

            "op_clientes_labels": cli_labels,
            "op_clientes_series": cli_series,

            "op_entregadas_hoy": entregadas_hoy,
            "op_pendientes_hoy": pendientes_hoy,

            "op_servicios": op_servicios,

            "filtros_clientes": filtros_clientes,
            "filtros_vendedores": filtros_vendedores,
            "filtros_pv": [],
            "filtros_proveedor": [],

            # rango activo
            "desde": desde, "hasta": hasta, "rango": self.request.GET.get("rango") or "mes",
        })
        return ctx


# =========================
#        ANALÍTICA: CxC
# =========================
class CarteraView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/cartera.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = localdate()
        desde, hasta, _label = _parse_rango(self.request)

        base = _empresa_serv_qs().filter(ruta__fecha_salida__range=(desde, hasta))

        # ---------------- Cartera total (saldo no pagado) ----------------
        # saldo = CASE estado_pago != 'PAG' THEN (valor - anticipo) ELSE 0
        saldo_expr = Case(
            When(estado_pago="PAG", then=Value(0)),
            default=F("valor") - Coalesce(F("anticipo"), Value(0)),
            output_field=IntegerField(),
        )

        cartera_total = base.aggregate(t=Coalesce(Sum(saldo_expr), 0))["t"] or 0

        # Clientes con saldo
        por_cliente = (base
                       .values("cliente__id", "cliente__nombre")
                       .annotate(saldo=Coalesce(Sum(saldo_expr), 0),
                                 max_dias=Coalesce(
                                     # días desde fecha de la ruta
                                     ExpressionWrapper(
                                         Value(hoy) - F("ruta__fecha_salida"),
                                         output_field=models.DurationField()
                                     ),
                                     Value(timedelta(0))
                                 ))
                       .order_by("-saldo"))

        top_deudores = []
        clientes_con_saldo = 0
        for c in por_cliente:
            s = int(c["saldo"] or 0)
            if s > 0:
                clientes_con_saldo += 1
                # max_dias es duration total de la última fila del grupo; como hay agrupación,
                # tomaremos días a partir de fecha más antigua si quieres, pero aquí ponemos "—" si no aplica
                top_deudores.append({
                    "nombre": c["cliente__nombre"] or "—",
                    "saldo": s,
                    "max_dias": None,  # si quieres precisión, debes calcular sobre subquery por cliente
                })
        top_deudores = top_deudores[:10]
        top_deudor = top_deudores[0] if top_deudores else {"nombre": "—", "saldo": 0}

        # ---------------- Aging buckets ----------------
        # días = hoy - ruta__fecha_salida
        dias_expr = ExpressionWrapper(
            Value(hoy) - F("ruta__fecha_salida"),
            output_field=models.DurationField()
        )

        # Para agrupar por rangos, sacamos días como entero (aprox)
        # Dividimos por 86400 para obtener días. Django no tiene extracción directa de days en DurationField
        # así que hacemos buckets con comparaciones aproximadas usando timedelta.
        b0_30 = base.filter(estado_pago__in=["PEND", "ANT"]).filter(ruta__fecha_salida__gte=hoy - timedelta(days=30)).aggregate(t=Coalesce(Sum(F("valor") - Coalesce(F("anticipo"), Value(0))), 0))["t"] or 0
        b31_60 = base.filter(estado_pago__in=["PEND", "ANT"]).filter(
            ruta__fecha_salida__lt=hoy - timedelta(days=30),
            ruta__fecha_salida__gte=hoy - timedelta(days=60)
        ).aggregate(t=Coalesce(Sum(F("valor") - Coalesce(F("anticipo"), Value(0))), 0))["t"] or 0
        b61_90 = base.filter(estado_pago__in=["PEND", "ANT"]).filter(
            ruta__fecha_salida__lt=hoy - timedelta(days=60),
            ruta__fecha_salida__gte=hoy - timedelta(days=90)
        ).aggregate(t=Coalesce(Sum(F("valor") - Coalesce(F("anticipo"), Value(0))), 0))["t"] or 0
        b90p = base.filter(estado_pago__in=["PEND", "ANT"]).filter(
            ruta__fecha_salida__lt=hoy - timedelta(days=90)
        ).aggregate(t=Coalesce(Sum(F("valor") - Coalesce(F("anticipo"), Value(0))), 0))["t"] or 0

        aging = [int(b0_30), int(b31_60), int(b61_90), int(b90p)]
        total_aging = sum(aging) or 1
        aging_pct = [round(x * 100.0 / total_aging, 1) for x in aging]

        # ---------------- Cobrado del MES + % ----------------
        first_month = date(hoy.year, hoy.month, 1)
        mes_qs = _empresa_serv_qs().filter(ruta__fecha_salida__range=(first_month, hoy))
        cobrado_mes = mes_qs.aggregate(t=Coalesce(Sum("anticipo"), 0))["t"] or 0
        fact_mes    = mes_qs.aggregate(t=Coalesce(Sum("valor"), 0))["t"] or 0
        pct_mes     = (cobrado_mes / fact_mes * 100.0) if fact_mes else 0.0

        # ---------------- DSO (aprox) ----------------
        # DSO ≈ Cartera total / Ventas diarias promedio (últimos 90 días)
        ult90_from = hoy - timedelta(days=89)
        v90 = _empresa_serv_qs().filter(ruta__fecha_salida__range=(ult90_from, hoy))
        fact_90 = v90.aggregate(t=Coalesce(Sum("valor"), 0))["t"] or 0
        avg_daily = (fact_90 / 90.0) if fact_90 else 0.0
        dso = round(cartera_total / avg_daily, 1) if avg_daily > 0 else "—"

        # Selects de filtros (cliente + vendedor)
        filtros_clientes = (base
                            .values("cliente__id", "cliente__nombre")
                            .annotate(n=Count("id"))
                            .order_by("cliente__nombre"))
        filtros_clientes = [{"id": i["cliente__id"], "nombre": i["cliente__nombre"] or "—"} for i in filtros_clientes if i["cliente__id"]]
        filtros_vendedores = (base
                              .values("ruta__conductor__id", "ruta__conductor__username")
                              .annotate(n=Count("id")).order_by("ruta__conductor__username"))
        filtros_vendedores = [{"id": i["ruta__conductor__id"], "username": i["ruta__conductor__username"] or "—"} for i in filtros_vendedores if i["ruta__conductor__id"]]

        ctx.update({
            "cx_total": int(cartera_total),
            "cx_clientes_con_saldo": int(clientes_con_saldo),
            "cx_cobrado_mes": int(cobrado_mes),
            "cx_pct_mes": pct_mes,
            "cx_dso": dso,
            "cx_top_deudor": top_deudor,
            "cx_top_deudores": top_deudores,

            "cx_aging": aging,
            "cx_aging_pct": aging_pct,

            "filtros_clientes": filtros_clientes,
            "filtros_vendedores": filtros_vendedores,
        })
        return ctx


# -------- APIs ----------
class RutasActivasLiteAPI(LoginRequiredMixin, View):
    def get(self, request):
        limit = request.GET.get("limit")
        lim = int(limit) if (limit and str(limit).isdigit()) else 6
        data = _rutas_activas_cards(limit=lim)
        return JsonResponse({"routes": data})

class RutaPointsAPI(LoginRequiredMixin, View):
    """Devuelve puntos (lat,lon) ordenados temporalmente desde los servicios de la ruta."""
    def get(self, request, pk: int):
        try:
            ruta = _rutas_qs_base().get(pk=pk)
        except Ruta.DoesNotExist:
            raise Http404("Ruta no encontrada")
        pts = _route_points_from_servicios(ruta)[:1000]
        return JsonResponse({"id": ruta.id, "points": pts})

class RutaRecorridoView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/ruta_recorrido.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = kwargs.get("pk")
        try:
            ruta = _rutas_qs_base().get(pk=pk)
        except Ruta.DoesNotExist:
            raise Http404("Ruta no encontrada")

        veh = getattr(ruta, "vehiculo", None)
        placa = getattr(veh, "placa", "s/n")
        conductor = getattr(ruta, "conductor", None)
        conductor_name = ""
        if conductor:
            conductor_name = (
                f"{getattr(conductor,'first_name','')} {getattr(conductor,'last_name','')}".strip()
                or getattr(conductor, "username", "")
            )

        ctx.update({
            "ruta_id": ruta.id,
            "ruta_nombre": getattr(ruta, "nombre", f"Ruta #{ruta.id}"),
            "placa": placa,
            "conductor": conductor_name,
        })
        return ctx
