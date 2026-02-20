from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.timezone import localdate
from datetime import date
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.functions import Coalesce
from django.db.models import Sum

from acarreapp.tenancy import get_current_empresa
from servicios.models import Servicio
from rutas.models import Ruta

# === Permiso gerente ===
class GerenteRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_denied_message = "No tienes permisos para ver esta página."
    def test_func(self):
        u = self.request.user
        rol = (getattr(getattr(u, "userprofile", None), "rol", "") or "").upper()
        return u.is_superuser or u.is_staff or rol == "GERENTE"

# === Helpers multi-empresa ===
def _empresa_serv(qs):
    emp = get_current_empresa()
    return qs.filter(ruta__empresa=emp) if emp else qs.none()

def _empresa_ruta(qs):
    emp = get_current_empresa()
    return qs.filter(empresa=emp) if emp else qs.none()

def _rutas_activas_qs():
    qs = _empresa_ruta(Ruta.objects.select_related("vehiculo", "conductor"))
    if hasattr(Ruta, "estado"):
        qs = qs.filter(estado="ACTIVA")
    elif hasattr(Ruta, "cerrada"):
        qs = qs.filter(cerrada=False)
    else:
        qs = qs.filter(cierre__isnull=True)
    return qs

def _servicios_no_entregados(qs):
    if hasattr(Servicio, "entregado"):
        return qs.filter(entregado=False)
    return qs.filter(entregado_en__isnull=True)

def _servicios_activos_qs():
    base = _empresa_serv(Servicio.objects.select_related("ruta", "cliente"))
    return _servicios_no_entregados(base).filter(ruta__in=_rutas_activas_qs())

# === Vistas dashboard ===
class DashboardHomeView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = localdate()
        primer_dia_mes = date(hoy.year, hoy.month, 1)
        serv = _empresa_serv(Servicio.objects.select_related("ruta"))

        facturado = serv.filter(ruta__fecha_salida__range=(primer_dia_mes, hoy)) \
                        .aggregate(t=Coalesce(Sum("valor"), 0))["t"] or 0
        cobrado   = serv.filter(ruta__fecha_salida__range=(primer_dia_mes, hoy)) \
                        .aggregate(t=Coalesce(Sum("anticipo"), 0))["t"] or 0
        cartera = int(facturado) - int(cobrado)

        u = self.request.user
        nombre_usuario = (f"{getattr(u,'first_name','')} {getattr(u,'last_name','')}".strip()
                          or getattr(u, "username", ""))

        ctx.update({
            "hoy": hoy,
            "kpi_facturado": int(facturado),
            "kpi_cobrado": int(cobrado),
            "kpi_cartera": int(cartera),
            "servicios_activos": _servicios_activos_qs().count(),
            "rutas_activas": _rutas_activas_qs().count(),
            "nombre_usuario": nombre_usuario,
        })
        return ctx

class OperacionView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/operacion.html"

class CarteraView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/cartera.html"

# === Redirecciones por rol ===
def _rol(user):
    return (getattr(getattr(user, "userprofile", None), "rol", "") or "").upper()

@login_required
def post_login_redirect(request):
    u = request.user
    rol = _rol(u)
    if u.is_superuser or u.is_staff or rol == "GERENTE":
        return redirect("dashboard:home")     # ← usa 'home'
    if rol == "CONDUCTOR":
        return redirect("rutas:list")         # ← conductor a /rutas/ (tu ListView ya filtra activas propias)
    return redirect("servicios:mis")          # fallback

@login_required
def index(request):
    u = request.user
    rol = _rol(u)
    if u.is_superuser or u.is_staff or rol == "GERENTE":
        return redirect("dashboard:home")
    if rol == "CONDUCTOR":
        return redirect("rutas:list")
    return redirect("servicios:mis")
