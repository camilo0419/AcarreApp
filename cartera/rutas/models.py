from django.db import models
from django.contrib.auth.models import User
from empresa.models import Empresa, Vehiculo

class Ruta(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    fecha_salida = models.DateField()
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT)
    conductor = models.ForeignKey(User, on_delete=models.PROTECT)
    base_efectivo = models.DecimalField(max_digits=10, decimal_places=2, default=200000)
    estado = models.CharField(max_length=20, choices=[('ACTIVA', 'Activa'), ('CERRADA', 'Cerrada')], default='ACTIVA')

    # 🆕 nuevo campo
    nombre = models.CharField(max_length=150, blank=True, help_text="Ej: Jardin - Medellin - Jardin")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre or f"Ruta {self.id} ({self.fecha_salida})"


class MovimientoCaja(models.Model):
    TIPO = [('INGRESO','Ingreso'), ('GASTO','Gasto')]

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TIPO)
    concepto = models.CharField(max_length=120)
    valor = models.IntegerField()
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    timestamp = models.DateTimeField(auto_now_add=True)

class CierreRuta(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    ruta = models.OneToOneField(Ruta, on_delete=models.PROTECT, related_name='cierre')
    total_servicios = models.PositiveIntegerField(default=0)
    total_cobrado = models.IntegerField(default=0)
    total_pendiente = models.IntegerField(default=0)
    total_gastos = models.IntegerField(default=0)
    total_ingresos = models.IntegerField(default=0)
    utilidad_neta = models.IntegerField(default=0)
    generado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    generado_en = models.DateTimeField(auto_now_add=True)
