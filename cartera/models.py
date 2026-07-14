from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class CarteraEmpresaConfig(models.Model):
    empresa = models.OneToOneField(
        "empresa.Empresa",
        on_delete=models.CASCADE,
        related_name="cartera_config",
    )
    nombre_emisor = models.CharField(max_length=160, blank=True)
    nit_emisor = models.CharField(max_length=40, blank=True)
    direccion_emisor = models.CharField(max_length=220, blank=True)
    telefono_emisor = models.CharField(max_length=80, blank=True)
    email_emisor = models.EmailField(blank=True)
    logo_static_path = models.CharField(max_length=180, default="icons/Logo.png")
    prefijo_cuenta_cobro = models.CharField(max_length=12, default="CC")
    proximo_consecutivo = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    notas_estado_cuenta = models.TextField(blank=True)
    notas_cuenta_cobro = models.TextField(blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuracion de cartera"
        verbose_name_plural = "configuraciones de cartera"

    def __str__(self):
        return f"Cartera - {self.empresa}"

    @property
    def nombre_para_pdf(self):
        return self.nombre_emisor or self.empresa.nombre

    @property
    def nit_para_pdf(self):
        return self.nit_emisor or self.empresa.nit


class PagoServicio(models.Model):
    MEDIO_EFECTIVO = "EFECTIVO"
    MEDIO_TRANSFERENCIA = "TRANSFERENCIA"
    MEDIO_NEQUI = "NEQUI"
    MEDIO_DAVIPLATA = "DAVIPLATA"
    MEDIO_TARJETA = "TARJETA"
    MEDIO_ANTICIPO = "ANTICIPO"
    MEDIO_AJUSTE = "AJUSTE"
    MEDIO_OTRO = "OTRO"
    MEDIOS = [
        (MEDIO_EFECTIVO, "Efectivo"),
        (MEDIO_TRANSFERENCIA, "Transferencia"),
        (MEDIO_NEQUI, "Nequi"),
        (MEDIO_DAVIPLATA, "Daviplata"),
        (MEDIO_TARJETA, "Tarjeta"),
        (MEDIO_ANTICIPO, "Anticipo legacy"),
        (MEDIO_AJUSTE, "Ajuste autorizado"),
        (MEDIO_OTRO, "Otro"),
    ]

    empresa = models.ForeignKey("empresa.Empresa", on_delete=models.PROTECT, related_name="pagos_cartera")
    servicio = models.ForeignKey("servicios.Servicio", on_delete=models.PROTECT, related_name="pagos")
    cliente = models.ForeignKey("empresa.Cliente", on_delete=models.PROTECT, related_name="pagos_cartera")
    ruta = models.ForeignKey("rutas.Ruta", on_delete=models.PROTECT, related_name="pagos_cartera")
    valor = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    medio_pago = models.CharField(max_length=20, choices=MEDIOS, default=MEDIO_EFECTIVO)
    fecha_pago = models.DateField(default=timezone.localdate)
    referencia = models.CharField(max_length=120, blank=True)
    observacion = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_cartera_registrados",
    )
    impacta_caja = models.BooleanField(default=False)
    movimiento_caja = models.OneToOneField(
        "rutas.MovimientoCaja",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pago_servicio",
    )
    anulado = models.BooleanField(default=False)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_cartera_anulados",
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=240, blank=True)
    movimiento_reversion = models.OneToOneField(
        "rutas.MovimientoCaja",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pago_servicio_revertido",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_pago", "-creado_en", "-id"]
        indexes = [
            models.Index(fields=["empresa", "fecha_pago"]),
            models.Index(fields=["servicio", "anulado"]),
            models.Index(fields=["cliente", "fecha_pago"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(valor__gt=0), name="pago_servicio_valor_positivo"),
        ]

    def __str__(self):
        return f"Pago #{self.pk} servicio #{self.servicio_id} - {self.valor}"


class CuentaCobro(models.Model):
    empresa = models.ForeignKey("empresa.Empresa", on_delete=models.PROTECT, related_name="cuentas_cobro")
    servicio = models.OneToOneField("servicios.Servicio", on_delete=models.PROTECT, related_name="cuenta_cobro")
    cliente = models.ForeignKey("empresa.Cliente", on_delete=models.PROTECT, related_name="cuentas_cobro")
    consecutivo = models.PositiveIntegerField()
    numero = models.CharField(max_length=32)
    emitida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuentas_cobro_emitidas",
    )
    emitida_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-emitida_en", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "consecutivo"], name="cuenta_cobro_consecutivo_empresa"),
            models.UniqueConstraint(fields=["empresa", "numero"], name="cuenta_cobro_numero_empresa"),
        ]

    def __str__(self):
        return self.numero
