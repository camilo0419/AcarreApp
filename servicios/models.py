from django.utils import timezone
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

class Servicio(models.Model):
    PENDIENTE = 'PEND'
    ANTICIPO = 'ANT'
    PAGADO = 'PAG'
    ESTADOS = [(PENDIENTE,'Pendiente'), (ANTICIPO,'Recibir anticipo'), (PAGADO,'Pagado')]

    cliente = models.ForeignKey('empresa.Cliente', on_delete=models.PROTECT)
    ruta = models.ForeignKey('rutas.Ruta', on_delete=models.CASCADE, related_name='servicios')

    valor = models.PositiveIntegerField()
    estado_pago = models.CharField(max_length=4, choices=ESTADOS, default=PENDIENTE)
    anticipo = models.PositiveIntegerField(default=0)

    origen = models.CharField(max_length=200, blank=True)
    destino = models.CharField(max_length=200, blank=True)
    notas = models.TextField(blank=True)

    # Estado operativo
    recogido = models.BooleanField(default=False)
    entregado = models.BooleanField(default=False)

    # 🔙 De vuelta: timestamps + geolocalización
    recogido_en = models.DateTimeField(null=True, blank=True)
    lat_recogida = models.FloatField(null=True, blank=True)
    lon_recogida = models.FloatField(null=True, blank=True)

    entregado_en = models.DateTimeField(null=True, blank=True)
    lat_entrega = models.FloatField(null=True, blank=True)
    lon_entrega = models.FloatField(null=True, blank=True)

    # ➕ Orden dentro de la ruta (para drag & drop del gerente)
    orden = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        # Mantenemos determinismo por orden dentro de la ruta y, como fallback, por id
        ordering = ['ruta', 'orden', 'id']

    # --- validaciones pago ---
    def clean(self):
        if self.valor is None or self.valor < 0:
            raise ValidationError({'valor': 'Debe ser un valor positivo.'})
        if self.estado_pago == self.PENDIENTE and self.anticipo != 0:
            raise ValidationError({'anticipo': 'Deja el anticipo en 0 cuando el estado es Pendiente.'})
        if self.estado_pago == self.ANTICIPO:
            if self.anticipo <= 0:
                raise ValidationError({'anticipo': 'Ingresa un anticipo mayor a 0.'})
            if self.anticipo > self.valor:
                raise ValidationError({'anticipo': 'El anticipo no puede ser mayor al valor del servicio.'})
        if self.estado_pago == self.PAGADO:
            self.anticipo = self.valor

    def save(self, *args, **kwargs):
        # Regla de anticipo según estado
        if self.estado_pago == self.PAGADO:
            self.anticipo = self.valor
        elif self.estado_pago == self.PENDIENTE:
            self.anticipo = 0

        # Autonumerar 'orden' al final de la ruta cuando venga vacío/0
        if self.ruta_id and (not self.orden or self.orden == 0):
            # para no provocar query extra cuando ya existe y tiene orden
            from servicios.models import Servicio as ServicioModel  # evitar import circular
            qs = ServicioModel.objects.filter(ruta_id=self.ruta_id).exclude(pk=self.pk).order_by('-orden')
            last = qs.first()
            self.orden = (last.orden + 1) if last and last.orden else 1

        super().save(*args, **kwargs)

    @property
    def saldo_cartera(self):
        if self.estado_pago == self.PAGADO:
            return 0
        if self.estado_pago == self.PENDIENTE:
            return self.valor
        return max(self.valor - self.anticipo, 0)

    # helpers para marcar con fecha/ubicación
    def marcar_recogido(self, lat=None, lon=None):
        self.recogido = True
        if not self.recogido_en:
            self.recogido_en = timezone.now()
        if lat is not None: self.lat_recogida = float(lat)
        if lon is not None: self.lon_recogida = float(lon)

    def marcar_entregado(self, lat=None, lon=None):
        self.entregado = True
        if not self.entregado_en:
            self.entregado_en = timezone.now()
        if lat is not None: self.lat_entrega = float(lat)
        if lon is not None: self.lon_entrega = float(lon)


class ServicioComentario(models.Model):
    servicio = models.ForeignKey('Servicio', on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    texto = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']  # más reciente primero

    def __str__(self):
        return f"Coment #{self.pk} en Serv #{self.servicio_id}"
