from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth.views import LogoutView
from . import views  # index y post_login_redirect

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/logout/", LogoutView.as_view(next_page="login"), name="logout"),

    # Apps
    path("rutas/", include(("rutas.urls", "rutas"), namespace="rutas")),
    path("servicios/", include(("servicios.urls", "servicios"), namespace="servicios")),
    path("cartera/", include(("cartera.urls", "cartera"), namespace="cartera")),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),

    path("post-login/", views.post_login_redirect, name="post_login"),
    path("", views.index, name="index"),
    path("index/", views.index),

    # alias opcional SOLO para login (no para logout)
    path("account/login/", RedirectView.as_view(pattern_name="login", permanent=False)),
]
