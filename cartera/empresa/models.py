from django.db import models
from django.utils.text import slugify

class Empresa(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    nit = models.CharField(max_length=30, blank=True)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

class Cliente(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    nombre = models.CharField(max_length=120)
    contacto = models.CharField(max_length=120, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = [('empresa','nombre')]
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class Vehiculo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    placa = models.CharField(max_length=15)
    marca = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=60, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = [('empresa','placa')]
        ordering = ['placa']

    def __str__(self):
        return self.placa
