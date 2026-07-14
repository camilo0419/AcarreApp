import unittest
from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from empresa.models import Cliente, Empresa, Vehiculo
from rutas.models import CierreRuta, MovimientoCaja, Ruta
from rutas.services import cerrar_ruta
from servicios.models import Servicio
from usuarios.models import UserProfile

from .models import CarteraEmpresaConfig, CuentaCobro, PagoServicio
from .services import obtener_o_crear_cuenta_cobro, registrar_pago_servicio

try:
    import weasyprint  # noqa: F401

    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], VAPID_PRIVATE_KEY="")
class CarteraBusinessTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(nombre="Empresa A", slug="empresa-a", nit="900123")
        self.empresa_b = Empresa.objects.create(nombre="Empresa B", slug="empresa-b", nit="900999")

        self.gerente_a = User.objects.create_user("gerente_a", password="pass")
        self.gerente_b = User.objects.create_user("gerente_b", password="pass")
        self.conductor_a = User.objects.create_user("conductor_a", password="pass")

        UserProfile.objects.create(user=self.gerente_a, empresa=self.empresa_a, rol="GERENTE")
        UserProfile.objects.create(user=self.gerente_b, empresa=self.empresa_b, rol="GERENTE")
        UserProfile.objects.create(user=self.conductor_a, empresa=self.empresa_a, rol="CONDUCTOR")

        self.vehiculo_a = Vehiculo.objects.create(empresa=self.empresa_a, placa="AAA123")
        self.vehiculo_b = Vehiculo.objects.create(empresa=self.empresa_b, placa="BBB123")
        self.cliente_a = Cliente.objects.create(empresa=self.empresa_a, nombre="Cliente A", telefono="300")
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
            conductor=self.gerente_b,
            nombre="Ruta B",
            base_efectivo=100,
        )
        self.servicio_a = Servicio.objects.create(
            ruta=self.ruta_a,
            cliente=self.cliente_a,
            valor=1000,
            estado_pago=Servicio.ANTICIPO,
            anticipo=400,
            origen="Bodega",
            destino="Cliente",
        )
        self.servicio_b = Servicio.objects.create(
            ruta=self.ruta_b,
            cliente=self.cliente_b,
            valor=700,
            origen="Otro origen",
            destino="Otro destino",
        )

    def test_dashboard_is_manager_only_and_company_scoped(self):
        self.client.force_login(self.conductor_a)
        self.assertEqual(self.client.get(reverse("cartera:dashboard")).status_code, 403)

        self.client.force_login(self.gerente_a)
        response = self.client.get(reverse("cartera:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente A")
        self.assertNotContains(response, "Cliente B")

    def test_partial_payment_creates_history_and_cash_movement_without_overpay(self):
        pago = registrar_pago_servicio(
            self.servicio_a.pk,
            empresa=self.empresa_a,
            usuario=self.gerente_a,
            valor=200,
            medio_pago=PagoServicio.MEDIO_EFECTIVO,
        )
        self.assertTrue(pago.impacta_caja)
        self.assertIsNotNone(pago.movimiento_caja_id)

        self.servicio_a.refresh_from_db()
        self.assertEqual(self.servicio_a.anticipo, 600)
        self.assertEqual(self.servicio_a.estado_pago, Servicio.ANTICIPO)
        self.assertEqual(self.servicio_a.saldo_cartera, 400)
        self.assertEqual(PagoServicio.objects.filter(servicio=self.servicio_a, anulado=False).count(), 2)
        self.assertEqual(MovimientoCaja.objects.filter(ruta=self.ruta_a, tipo="INGRESO").count(), 1)

        with self.assertRaises(ValidationError):
            registrar_pago_servicio(
                self.servicio_a.pk,
                empresa=self.empresa_a,
                usuario=self.gerente_a,
                valor=401,
                medio_pago=PagoServicio.MEDIO_EFECTIVO,
            )
        self.servicio_a.refresh_from_db()
        self.assertEqual(self.servicio_a.anticipo, 600)
        self.assertEqual(PagoServicio.objects.filter(servicio=self.servicio_a, anulado=False).count(), 2)

    def test_payment_after_route_close_does_not_mutate_cash_or_existing_closure(self):
        cierre = cerrar_ruta(self.ruta_a, self.gerente_a)
        self.assertEqual(cierre.total_cobrado, 400)
        self.assertEqual(cierre.total_pendiente, 600)

        pago = registrar_pago_servicio(
            self.servicio_a.pk,
            empresa=self.empresa_a,
            usuario=self.gerente_a,
            valor=200,
            medio_pago=PagoServicio.MEDIO_TRANSFERENCIA,
        )
        self.assertFalse(pago.impacta_caja)
        self.assertIsNone(pago.movimiento_caja_id)
        self.assertEqual(MovimientoCaja.objects.filter(ruta=self.ruta_a).count(), 0)

        self.servicio_a.refresh_from_db()
        self.assertEqual(self.servicio_a.anticipo, 600)
        cierre.refresh_from_db()
        self.assertEqual(cierre.total_cobrado, 400)
        self.assertEqual(cierre.total_pendiente, 600)
        self.assertEqual(CierreRuta.objects.count(), 1)

    def test_payment_views_reject_get_mutation_and_overpay(self):
        self.client.force_login(self.gerente_a)
        response = self.client.get(reverse("cartera:registrar_pago", args=[self.servicio_a.id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("cartera:registrar_pago", args=[self.servicio_a.id]),
            {"valor": "9999", "medio_pago": PagoServicio.MEDIO_EFECTIVO, "fecha_pago": date.today().isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PagoServicio.objects.filter(servicio=self.servicio_a).count(), 0)

        pago = registrar_pago_servicio(
            self.servicio_a.pk,
            empresa=self.empresa_a,
            usuario=self.gerente_a,
            valor=100,
        )
        response = self.client.get(reverse("cartera:anular_pago", args=[pago.id]))
        self.assertEqual(response.status_code, 405)

    def test_cuenta_cobro_consecutive_is_company_scoped_and_idempotent(self):
        config = CarteraEmpresaConfig.objects.create(
            empresa=self.empresa_a,
            nombre_emisor="Transportes A",
            prefijo_cuenta_cobro="AC",
            proximo_consecutivo=5,
        )
        cuenta_1 = obtener_o_crear_cuenta_cobro(self.servicio_a, self.gerente_a)
        cuenta_2 = obtener_o_crear_cuenta_cobro(self.servicio_a, self.gerente_a)
        config.refresh_from_db()

        self.assertEqual(cuenta_1.pk, cuenta_2.pk)
        self.assertEqual(cuenta_1.numero, "AC-000005")
        self.assertEqual(config.proximo_consecutivo, 6)
        self.assertEqual(CuentaCobro.objects.count(), 1)

    @unittest.skipUnless(HAS_WEASYPRINT, "WeasyPrint no esta instalado en el entorno de prueba.")
    def test_pdf_endpoints_generate_pdf_bytes(self):
        self.client.force_login(self.gerente_a)
        estado = self.client.get(reverse("cartera:estado_cuenta_pdf", args=[self.cliente_a.id]))
        self.assertEqual(estado.status_code, 200)
        self.assertEqual(estado["Content-Type"], "application/pdf")
        self.assertTrue(estado.content.startswith(b"%PDF"))

        cuenta = self.client.get(reverse("cartera:cuenta_cobro_pdf", args=[self.servicio_a.id]))
        self.assertEqual(cuenta.status_code, 200)
        self.assertEqual(cuenta["Content-Type"], "application/pdf")
        self.assertTrue(cuenta.content.startswith(b"%PDF"))
