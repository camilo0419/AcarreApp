# servicios/apps.py
from django.apps import AppConfig

class ServiciosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servicios"

    def ready(self):
        from . import signals  # <-- registra señales
