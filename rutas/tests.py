from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from acarreapp.tenancy import set_current_empresa
from cartera.queries import cartera_resumen
from empresa.models import Cliente, Empresa, Vehiculo
from servicios.models import Servicio
from usuarios.models import UserProfile

from .models import MovimientoCaja, Ruta
from .services import cerrar_ruta


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], VAPID_PRIVATE_KEY="")
class AcarreAppSecurityAndBusinessTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(nombre="Empresa A", slug="empresa-a")
        self.empresa_b = Empresa.objects.create(nombre="Empresa B", slug="empresa-b")

        self.gerente_a = User.objects.create_user("gerente_a", password="pass")
        self.gerente_b = User.objects.create_user("gerente_b", password="pass")
        self.conductor_a = User.objects.create_user("conductor_a", password="pass")
        self.conductor_b = User.objects.create_user("conductor_b", password="pass")

        UserProfile.objects.create(user=self.gerente_a, empresa=self.empresa_a, rol="GERENTE")
        UserProfile.objects.create(user=self.gerente_b, empresa=self.empresa_b, rol="GERENTE")
        UserProfile.objects.create(user=self.conductor_a, empresa=self.empresa_a, rol="CONDUCTOR")
        UserProfile.objects.create(user=self.conductor_b, empresa=self.empresa_b, rol="CONDUCTOR")

        self.vehiculo_a = Vehiculo.objects.create(empresa=self.empresa_a, placa="AAA123")
        self.vehiculo_b = Vehiculo.objects.create(empresa=self.empresa_b, placa="BBB123")
        self.cliente_a = Cliente.objects.create(empresa=self.empresa_a, nombre="Cliente A")
        self.cliente_b = Cliente.objects.create(empresa=self.empresa_b, nombre="Cliente B")

        self.ruta_a = Ruta.objects.create(
            empresa=self.empresa_a,
            fecha_salida=date.today(),
            vehiculo=self.vehiculo_a,
            conductor=self.conductor_a,
            nombre="Ruta A",
            base_efectivo=100,
        )
        self.ruta_b = Ruta.objects.create(
            empresa=self.empresa_b,
            fecha_salida=date.today(),
            vehiculo=self.vehiculo_b,
            conductor=self.conductor_b,
            nombre="Ruta B",
            base_efectivo=100,
        )
        self.servicio_a = Servicio.objects.create(
            ruta=self.ruta_a,
            cliente=self.cliente_a,
            valor=1000,
            estado_pago=Servicio.ANTICIPO,
            anticipo=400,
        )
        self.servicio_b = Servicio.objects.create(
            ruta=self.ruta_b,
            cliente=self.cliente_b,
            valor=500,
        )

    def test_reverse_mis_servicios_exists(self):
        self.assertEqual(reverse("servicios:mis"), "/servicios/mis/")

    def test_gerente_cannot_read_other_company_route_or_service(self):
        self.client.force_login(self.gerente_a)
        self.assertEqual(self.client.get(reverse("rutas:hoja", args=[self.ruta_b.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("servicios:detail", args=[self.servicio_b.id])).status_code, 404)

    def test_conductor_cannot_read_other_route_in_same_company(self):
        other = User.objects.create_user("other_a", password="pass")
        UserProfile.objects.create(user=other, empresa=self.empresa_a, rol="CONDUCTOR")
        ruta_other = Ruta.objects.create(
            empresa=self.empresa_a,
            fecha_salida=date.today(),
            vehiculo=self.vehiculo_a,
            conductor=other,
            nombre="Ruta other",
        )
        servicio_other = Servicio.objects.create(ruta=ruta_other, cliente=self.cliente_a, valor=10)

        self.client.force_login(self.conductor_a)
        self.assertEqual(self.client.get(reverse("rutas:hoja", args=[ruta_other.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("servicios:detail", args=[servicio_other.id])).status_code, 404)

    def test_get_does_not_modify_state_for_mutating_endpoints(self):
        self.client.force_login(self.gerente_a)
        checks = [
            reverse("rutas:borrar", args=[self.ruta_a.id]),
            reverse("rutas:cerrar", args=[self.ruta_a.id]),
            reverse("servicios:marcar_recogido", args=[self.servicio_a.id]),
            reverse("servicios:pago_efectivo", args=[self.servicio_a.id]),
        ]
        for url in checks:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405, url)

        self.ruta_a.refresh_from_db()
        self.servicio_a.refresh_from_db()
        self.assertEqual(self.ruta_a.estado, "ACTIVA")
        self.assertFalse(self.servicio_a.recogido)

    def test_conductor_can_mark_own_service_and_invalid_geo_is_ignored(self):
        self.client.force_login(self.conductor_a)
        response = self.client.post(
            reverse("servicios:marcar_recogido", args=[self.servicio_a.id]),
            {"lat": "999", "lon": "bad"},
        )
        self.assertEqual(response.status_code, 302)
        self.servicio_a.refresh_from_db()
        self.assertTrue(self.servicio_a.recogido)
        self.assertIsNone(self.servicio_a.lat_recogida)
        self.assertIsNone(self.servicio_a.lon_recogida)

    def test_cartera_includes_services_with_anticipo(self):
        total, por_cliente = cartera_resumen(self.empresa_a)
        self.assertEqual(total, 600)
        self.assertEqual(list(por_cliente)[0]["total"], 600)

    def test_cerrar_ruta_counts_anticipos_as_cobrado_and_saldo_as_pendiente(self):
        Servicio.objects.create(ruta=self.ruta_a, cliente=self.cliente_a, valor=300)
        MovimientoCaja.objects.create(
            empresa=self.empresa_a,
            ruta=self.ruta_a,
            tipo="GASTO",
            concepto="Peaje",
            valor=50,
            usuario=self.gerente_a,
        )
        cierre = cerrar_ruta(self.ruta_a, self.gerente_a)
        self.ruta_a.refresh_from_db()
        self.assertEqual(self.ruta_a.estado, "CERRADA")
        self.assertEqual(cierre.total_cobrado, 400)
        self.assertEqual(cierre.total_pendiente, 900)
        self.assertEqual(cierre.total_gastos, 50)

    def test_export_does_not_close_active_route(self):
        self.client.force_login(self.gerente_a)
        response = self.client.get(reverse("rutas:exportar_cierre_xlsx", args=[self.ruta_a.id]))
        self.assertEqual(response.status_code, 200)
        self.ruta_a.refresh_from_db()
        self.assertEqual(self.ruta_a.estado, "ACTIVA")
