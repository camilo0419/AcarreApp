from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q, Sum

from cartera.models import CuentaCobro, PagoServicio


class Command(BaseCommand):
    help = "Audita inconsistencias de cartera sin modificar datos."

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, help="Limita la auditoria a una empresa.")
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help="Retorna codigo no cero cuando se detectan inconsistencias.",
        )

    def handle(self, *args, **options):
        empresa_id = options.get("empresa_id")
        fail_on_issues = options.get("fail_on_issues")

        pagos = PagoServicio.objects.select_related(
            "empresa",
            "servicio",
            "servicio__ruta",
            "servicio__cliente",
            "cliente",
            "ruta",
            "movimiento_caja",
            "movimiento_reversion",
        )
        cuentas = CuentaCobro.objects.select_related("empresa", "servicio", "servicio__ruta", "cliente")
        if empresa_id:
            pagos = pagos.filter(empresa_id=empresa_id)
            cuentas = cuentas.filter(empresa_id=empresa_id)

        overpaid = (
            pagos.filter(anulado=False)
            .values("servicio_id", "servicio__valor", "servicio__cliente__nombre")
            .annotate(total=Sum("valor"))
            .filter(total__gt=F("servicio__valor"))
            .order_by("servicio_id")
        )
        payment_scope_mismatch = pagos.filter(
            ~Q(empresa_id=F("servicio__ruta__empresa_id"))
            | ~Q(cliente_id=F("servicio__cliente_id"))
            | ~Q(ruta_id=F("servicio__ruta_id"))
        )
        cash_missing = pagos.filter(anulado=False, impacta_caja=True, movimiento_caja__isnull=True)
        cash_unexpected = pagos.filter(impacta_caja=False, movimiento_caja__isnull=False)
        cash_value_mismatch = pagos.filter(movimiento_caja__isnull=False).filter(
            ~Q(movimiento_caja__tipo="INGRESO")
            | ~Q(movimiento_caja__valor=F("valor"))
            | ~Q(movimiento_caja__empresa_id=F("empresa_id"))
            | ~Q(movimiento_caja__ruta_id=F("ruta_id"))
        )
        reversal_missing = pagos.filter(anulado=True, movimiento_caja__isnull=False, movimiento_reversion__isnull=True)
        reversal_mismatch = pagos.filter(movimiento_reversion__isnull=False).filter(
            ~Q(movimiento_reversion__tipo="GASTO")
            | ~Q(movimiento_reversion__valor=F("valor"))
            | ~Q(movimiento_reversion__empresa_id=F("empresa_id"))
            | ~Q(movimiento_reversion__ruta_id=F("ruta_id"))
        )
        account_scope_mismatch = cuentas.filter(
            ~Q(empresa_id=F("servicio__ruta__empresa_id"))
            | ~Q(cliente_id=F("servicio__cliente_id"))
        )

        sections = [
            ("servicios_sobrepagados", overpaid),
            ("pagos_fuera_de_scope", payment_scope_mismatch),
            ("pagos_sin_movimiento_caja", cash_missing),
            ("pagos_con_caja_inesperada", cash_unexpected),
            ("pagos_con_movimiento_inconsistente", cash_value_mismatch),
            ("pagos_anulados_sin_reversion", reversal_missing),
            ("pagos_con_reversion_inconsistente", reversal_mismatch),
            ("cuentas_cobro_fuera_de_scope", account_scope_mismatch),
        ]

        self.stdout.write("Auditoria de cartera")
        if empresa_id:
            self.stdout.write(f"Empresa filtrada: {empresa_id}")

        total_issues = 0
        for label, qs in sections:
            count = qs.count()
            total_issues += count
            self.stdout.write(f"- {label}: {count}")
            for item in list(qs[:10]):
                self.stdout.write(f"  {item}")

        self.stdout.write(f"Total inconsistencias: {total_issues}")
        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS("Cartera sin inconsistencias detectadas."))
            return

        self.stdout.write(self.style.WARNING("Se detectaron inconsistencias. No se modifico ningun dato."))
        if fail_on_issues:
            raise CommandError("Auditoria de cartera encontro inconsistencias.")
