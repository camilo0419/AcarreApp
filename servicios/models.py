from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def _coord(value, minimum, maximum):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if minimum <= parsed <= maximum:
        return parsed
    return None


class Servicio(models.Model):
    PENDIENTE = "PEND"
    PARCIAL = "ANT"
    ANTICIPO = PARCIAL
    PAGADO = "PAG"
    ESTADOS = [(PENDIENTE, "Pendiente"), (PARCIAL, "Parcial"), (PAGADO, "Pagado")]

    cliente = models.ForeignKey("empresa.Cliente", on_delete=models.PROTECT)
    ruta = models.ForeignKey("rutas.Ruta", on_delete=models.CASCADE, related_name="servicios")

    valor = models.PositiveIntegerField(default=0)
    origen = models.CharField(max_length=200, blank=True)
    destino = models.CharField(max_length=200, blank=True)
    notas = models.TextField(blank=True)

    recogido = models.BooleanField(default=False)
    entregado = models.BooleanField(default=False)
    recogido_en = models.DateTimeField(null=True, blank=True)
    lat_recogida = models.FloatField(null=True, blank=True)
    lon_recogida = models.FloatField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    lat_entrega = models.FloatField(null=True, blank=True)
    lon_entrega = models.FloatField(null=True, blank=True)

    orden = models.PositiveIntegerField(default=0, db_index=True)
    cantidad = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Numero de unidades asociadas al servicio (minimo 1).",
    )

    class Meta:
        ordering = ["ruta", "orden", "id"]

    def clean(self):
        if self.valor is None or self.valor < 0:
            raise ValidationError({"valor": "Debe ser 0 o un valor positivo."})

    def save(self, *args, **kwargs):
        if self.ruta_id and (not self.orden or self.orden == 0):
            qs = Servicio.objects.filter(ruta_id=self.ruta_id).exclude(pk=self.pk).order_by("-orden")
            last = qs.first()
            self.orden = (last.orden + 1) if last and last.orden else 1
        super().save(*args, **kwargs)

    @property
    def total_pagado(self):
        if not self.pk:
            return 0
        from cartera.services import total_pagado_servicio

        return total_pagado_servicio(self)

    @property
    def saldo_cartera(self):
        return max(int(self.valor or 0) - int(self.total_pagado or 0), 0)

    @property
    def estado_pago(self):
        from cartera.services import estado_pago_para

        return estado_pago_para(self.valor, self.total_pagado)

    @property
    def anticipo(self):
        return self.total_pagado

    def get_estado_pago_display(self):
        return dict(self.ESTADOS).get(self.estado_pago, "Pendiente")

    def marcar_recogido(self, lat=None, lon=None):
        self.recogido = True
        if not self.recogido_en:
            self.recogido_en = timezone.now()
        lat = _coord(lat, -90, 90)
        lon = _coord(lon, -180, 180)
        if lat is not None:
            self.lat_recogida = lat
        if lon is not None:
            self.lon_recogida = lon

    def marcar_entregado(self, lat=None, lon=None):
        self.entregado = True
        if not self.entregado_en:
            self.entregado_en = timezone.now()
        lat = _coord(lat, -90, 90)
        lon = _coord(lon, -180, 180)
        if lat is not None:
            self.lat_entrega = lat
        if lon is not None:
            self.lon_entrega = lon


class ServicioComentario(models.Model):
    servicio = models.ForeignKey("Servicio", on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    texto = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Coment #{self.pk} en Serv #{self.servicio_id}"
