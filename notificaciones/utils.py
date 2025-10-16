import json
import logging
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from pywebpush import webpush, WebPushException
from .models import PushSubscription
from django.contrib.auth.models import Group    

logger = logging.getLogger(__name__)

def _urgency_headers(urgency: str | None):
    """
    Algunas versiones de pywebpush no aceptan urgency= como kwarg.
    Enviamos la urgencia por cabecera HTTP.
    Valores válidos: very-low, low, normal, high
    """
    u = (urgency or "normal").lower()
    if u not in {"very-low", "low", "normal", "high"}:
        u = "normal"
    return {"Urgency": u}

def _payload(title, body, data, *,
            icon="/static/icons/android-chrome-192x192.png",
            badge="/static/icons/favicon-32x32.png",
            tag="acarreapp",
            require_interaction=False,
            actions=None):
    return {
        "title": title,
        "body": body,
        "data": data or {},
        "icon": icon,
        "badge": badge,
        "tag": tag,
        "requireInteraction": bool(require_interaction),
        "actions": actions or [],
    }



def _vapid():
    return {
        "vapid_private_key": settings.VAPID_PRIVATE_KEY,
        # ¡OJO! No pases vapid_public_key aquí: pywebpush no lo admite en webpush()
        "vapid_claims": {"sub": settings.VAPID_SUBJECT},
    }

def send_webpush_to_user(user, title, body, data=None, urgency="normal"):
    """
    Envía una notificación a todas las suscripciones del usuario dado.
    """
    payload = _payload(
        title, body, data,
        require_interaction=True,  # que no desaparezca sola
        actions=[{"action": "ver", "title": "Ver detalle"}],
        tag="acarreapp-event",     # evita pila infinita si llegan muchas
    )

    vapid = _vapid()
    headers = _urgency_headers(urgency)

    subs = PushSubscription.objects.filter(user=user)
    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=json.dumps(payload),
                ttl=60,
                headers=headers,  # <-- aquí va la urgencia
                **vapid,
            )
            logger.info("Push enviado a %s -> %s", user, s.endpoint[:60])
        except WebPushException as e:
            status = getattr(e, "response", None).status_code if getattr(e, "response", None) else None
            text = getattr(e, "response", None).text if getattr(e, "response", None) else str(e)
            logger.error("WebPushException status=%s body=%s", status, text)
            if status in (404, 410):
                # endpoint inválido: lo limpiamos
                s.delete()
        except Exception as e:
            logger.exception("Error enviando push a %s: %s", user, e)

def send_webpush_to_users(users_qs, title, body, data=None, urgency="normal"):
    """
    Envía a todas las suscripciones de un queryset de usuarios.
    """
    payload = _payload(title, body, data)
    vapid = _vapid()
    headers = _urgency_headers(urgency)

    subs = PushSubscription.objects.filter(user__in=users_qs)
    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=json.dumps(payload),
                ttl=60,
                headers=headers,
                **vapid,
            )
        except WebPushException as e:
            status = getattr(e, "response", None).status_code if getattr(e, "response", None) else None
            if status in (404, 410):
                s.delete()
        except Exception:
            logger.exception("Error enviando push a endpoint %s", s.endpoint[:60])

def send_webpush_to_empresa(empresa, title, body, data=None, urgency="normal", exclude_user=None):
    """
    Envía una notificación a todos los usuarios activos de una empresa.
    Requiere que haya relación UserProfile -> empresa.
    """
    from usuarios.models import UserProfile  # evita ciclos
    User = get_user_model()

    users_qs = User.objects.filter(userprofile__empresa=empresa, is_active=True)
    if exclude_user is not None:
        users_qs = users_qs.exclude(pk=getattr(exclude_user, "pk", exclude_user))

    def _send():
        send_webpush_to_users(users_qs, title, body, data=data, urgency=urgency)

    try:
        # Si hay transacción en curso, enviamos después del commit
        transaction.on_commit(_send)
    except Exception:
        _send()

def _conductores_qs(empresa):
    """
    Intenta identificar conductores:
    1) Por Group 'Conductor'
    2) Por UserProfile.rol == 'conductor' (ajusta el valor si usas otro)
    3) Si no hay ninguna de las anteriores, devuelve queryset vacío
    """
    from usuarios.models import UserProfile
    User = get_user_model()

    # 1) Grupo "Conductor"
    try:
        g = Group.objects.get(name__iexact="Conductor")
        by_group = User.objects.filter(groups=g, userprofile__empresa=empresa, is_active=True)
        if by_group.exists():
            return by_group
    except Group.DoesNotExist:
        pass

    # 2) Perfil por rol (ajusta el nombre del campo/valor si difiere)
    try:
        by_role = User.objects.filter(userprofile__empresa=empresa,
                                      userprofile__rol__iexact="conductor",
                                      is_active=True)
        if by_role.exists():
            return by_role
    except Exception:
        pass

    # 3) Vacío si no podemos detectar
    return User.objects.none()

def _resto_empresa_qs(empresa, exclude_users_qs=None):
    from usuarios.models import UserProfile
    User = get_user_model()
    base = User.objects.filter(userprofile__empresa=empresa, is_active=True)
    if exclude_users_qs is not None:
        base = base.exclude(pk__in=list(exclude_users_qs.values_list("pk", flat=True)))
    return base