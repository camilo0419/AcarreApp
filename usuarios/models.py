from django.db import models
from django.contrib.auth.models import User
from empresa.models import Empresa

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, null=True)
    rol = models.CharField(max_length=20, choices=[('GERENTE','Gerente'),('CONDUCTOR','Conductor')])

    def __str__(self):
        return f"{self.user.username} ({self.rol})"
