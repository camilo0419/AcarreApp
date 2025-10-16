from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Servicio
from notificaciones.utils import (
    send_webpush_to_users,
    _conductores_qs,
    _resto_empresa_qs,
)

def _get_empresa_context_fallback():
    try:
        from acarreapp.tenancy import get_current_empresa
        return get_current_empresa()
    except Exception:
        return None


@receiver(post_save, sender=Servicio)
def servicio_created_notify(sender, instance, created, **kwargs):
    if not created:
        return

    # Empresa por la ruta del servicio o por el contexto tenancy
    ruta = getattr(instance, "ruta", None)
    empresa = getattr(ruta, "empresa", None) or _get_empresa_context_fallback()
    if not empresa:
        return

    # Segmentos: conductores (→ /rutas/mias/) y resto (→ detalle del servicio)
    conductores = _conductores_qs(empresa)
    resto = _resto_empresa_qs(empresa, exclude_users_qs=conductores)

    if conductores.exists():
        send_webpush_to_users(
            conductores,
            "📦 Nuevo servicio en tu ruta",
            f"Servicio #{instance.id}" + (f" agregado a la ruta #{ruta.id}" if ruta else ""),
            data={"url": "/rutas/mias/"},
        )

    if resto.exists():
        send_webpush_to_users(
            resto,
            "📦 Nuevo servicio creado",
            f"Servicio #{instance.id}" + (f" en ruta #{ruta.id}" if ruta else ""),
            data={"url": f"/servicios/{instance.id}/"},
        )
