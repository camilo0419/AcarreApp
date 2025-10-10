# acarreapp/views.py
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

@require_GET
def logout_get(request):
    """Cierra sesión con GET y redirige al login."""
    logout(request)
    return redirect('login')  # nombre provisto por django.contrib.auth.urls
