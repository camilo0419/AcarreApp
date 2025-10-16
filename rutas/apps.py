# rutas/apps.py
from django.apps import AppConfig

class RutasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rutas"

    def ready(self):
        from . import signals  # <-- registra señales
