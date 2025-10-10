from django.db import models
from .tenancy import get_current_empresa

class EmpresaQuerySet(models.QuerySet):
    def de_empresa_actual(self):
        emp = get_current_empresa()
        return self.filter(empresa=emp) if emp else self.none()

class EmpresaManager(models.Manager):
    def get_queryset(self):
        return EmpresaQuerySet(self.model, using=self._db)
    def de_empresa_actual(self):
        return self.get_queryset().de_empresa_actual()

class EmpresaScopedModel(models.Model):
    empresa = models.ForeignKey('empresa.Empresa', on_delete=models.PROTECT)

    objects = EmpresaManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.empresa_id:
            from .tenancy import get_current_empresa
            emp = get_current_empresa()
            if emp:
                self.empresa = emp
        super().save(*args, **kwargs)
