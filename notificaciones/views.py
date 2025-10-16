import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.shortcuts import render
from .models import PushSubscription
from .utils import send_webpush_to_user

@login_required
@require_POST
def subscribe(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
        sub = body.get("subscription", {})
        endpoint = sub.get("endpoint")
        keys = sub.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        ua = request.META.get("HTTP_USER_AGENT", "")

        if not (endpoint and p256dh and auth):
            return HttpResponseBadRequest("Invalid subscription")

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": request.user, "p256dh": p256dh, "auth": auth, "user_agent": ua},
        )
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

@login_required
def debug(request):
    return render(request, "notificaciones/debug.html")

@login_required
def test_push_me(request):
    send_webpush_to_user(
        request.user,
        "Ping AcarreApp",
        "Notificación de prueba",
        {"url": "/"},
        urgency="high",
    )
    return JsonResponse({"ok": True})

@login_required
def delete_my_subs(request):
    PushSubscription.objects.filter(user=request.user).delete()
    return JsonResponse({"ok": True})


@login_required
def status(request):
    from .models import PushSubscription
    n = PushSubscription.objects.filter(user=request.user).count()
    return JsonResponse({"server_subs": n})