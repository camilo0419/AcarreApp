# acarreapp/views.py
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from django.urls import reverse, NoReverseMatch

@require_http_methods(["GET", "POST"])
@login_required
def logout_view(request):
    """Acepta GET/POST y siempre redirige al login (o next)."""
    logout(request)
    next_url = (
        request.GET.get("next")
        or request.POST.get("next")
        or getattr(settings, "LOGOUT_REDIRECT_URL", None)
        or "login"
    )
    return redirect(next_url)

@login_required
def post_login_redirect(request):
    """Decide destino post-login según el rol."""
    user = request.user
    rol = getattr(getattr(user, "userprofile", None), "rol", "") or ""

    # Gerente / staff / superuser → Dashboard del gerente (si existe)
    if user.is_superuser or user.is_staff or rol == "GERENTE":
        try:
            url = reverse("dashboard:home_gerente")
        except NoReverseMatch:
            # fallback si aún no creas home_gerente
            try:
                url = reverse("dashboard:index")
            except NoReverseMatch:
                url = reverse("rutas:list")
        return redirect(url)

    # Conductor → listado de rutas (activas en tu filtro)
    return redirect("rutas:list")
