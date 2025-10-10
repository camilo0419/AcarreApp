# AcarreApp/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from .views import logout_get

urlpatterns = [
    path('admin/', admin.site.urls),

    path('accounts/logout/', logout_get, name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),

    # Apps con namespace
    path('rutas/', include(('rutas.urls', 'rutas'), namespace='rutas')),
    path('servicios/', include(('servicios.urls', 'servicios'), namespace='servicios')),
    path('cartera/', include(('cartera.urls', 'cartera'), namespace='cartera')),

    # Redirección inicial
    path('', RedirectView.as_view(pattern_name='servicios:mis', permanent=False)),

    path('cartera/', include('cartera.urls', namespace='cartera')),
]
