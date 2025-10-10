from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rutas.models import Ruta, MovimientoCaja
from servicios.models import Servicio
from empresa.models import Cliente, Vehiculo

class Command(BaseCommand):
    help = "Crea grupos Gerente y Conductor con permisos básicos"

    def handle(self, *args, **kwargs):
        gerente, _ = Group.objects.get_or_create(name='Gerente')
        conductor, _ = Group.objects.get_or_create(name='Conductor')

        modelos = [Ruta, MovimientoCaja, Servicio, Cliente, Vehiculo]
        for m in modelos:
            ct = ContentType.objects.get_for_model(m)
            perms = Permission.objects.filter(content_type=ct)
            gerente.permissions.add(*perms)

        for m in [Servicio, MovimientoCaja, Ruta]:
            ct = ContentType.objects.get_for_model(m)
            view = Permission.objects.get(codename=f'view_{m._meta.model_name}', content_type=ct)
            conductor.permissions.add(view)
        for m in [Servicio, MovimientoCaja]:
            ct = ContentType.objects.get_for_model(m)
            for codename in [f'add_{m._meta.model_name}', f'change_{m._meta.model_name}']:
                p = Permission.objects.get(codename=codename, content_type=ct)
                conductor.permissions.add(p)

        self.stdout.write(self.style.SUCCESS('✅ Grupos y permisos creados/actualizados'))
