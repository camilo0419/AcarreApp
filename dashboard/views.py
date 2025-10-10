# dashboard/views.py
from django.utils.timezone import localdate
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from rutas.models import Ruta
from servicios.models import Servicio

class GerenteRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_denied_message = "No tienes permisos para ver esta página."
    def test_func(self):
        u = self.request.user
        rol = getattr(getattr(u, "userprofile", None), "rol", "") or ""
        return u.is_superuser or u.is_staff or rol == "GERENTE"

class HomeGerenteView(GerenteRequiredMixin, TemplateView):
    template_name = "dashboard/home_gerente.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = localdate()

        rutas_activas = (Ruta.objects
                         .filter(estado="ACTIVA")
                         .select_related("vehiculo", "conductor")
                         .order_by("-fecha_salida")[:8])

        servicios_activos = Servicio.objects.filter(ruta__estado="ACTIVA")
        total_servicios_activos = servicios_activos.count()
        pendientes_entrega = servicios_activos.filter(entregado_en__isnull=True).count()

        ctx.update({
            "hoy": hoy,
            "rutas_activas": rutas_activas,
            "kpi_rutas_activas": rutas_activas.count(),
            "kpi_servicios_activos": total_servicios_activos,
            "kpi_pendientes_entrega": pendientes_entrega,
        })
        return ctx
