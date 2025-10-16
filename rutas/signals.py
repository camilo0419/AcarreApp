from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ruta
from notificaciones.utils import (
    send_webpush_to_users,
    _conductores_qs,
    _resto_empresa_qs,
)
from acarreapp.tenancy import get_current_empresa as _get_empresa_context_fallback


@receiver(post_save, sender=Ruta)
def ruta_created_notify(sender, instance: Ruta, created, **kwargs):
    if not created:
        return

    empresa = getattr(instance, "empresa", None) or _get_empresa_context_fallback()
    if not empresa:
        return

    # 1) Conductores → lista de “mis rutas”
    conductores = _conductores_qs(empresa)
    if conductores.exists():
        send_webpush_to_users(
            conductores,
            "🧭 Nueva ruta asignada",
            f"Ruta #{instance.id} creada para {getattr(instance, 'fecha_salida', '')}.",
            data={"url": "/rutas/mias/"},
            urgency="high",
        )

    # 2) Resto de la empresa → detalle de la ruta
    resto = _resto_empresa_qs(empresa, exclude_users_qs=conductores)
    if resto.exists():
        send_webpush_to_users(
            resto,
            "🧭 Nueva ruta creada",
            f"Ruta #{instance.id} creada para {getattr(instance, 'fecha_salida', '')}.",
            data={"url": f"/rutas/{instance.id}/detalle/"},
            urgency="normal",
        )
