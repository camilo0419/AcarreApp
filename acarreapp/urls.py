from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from .views import logout_view, post_login_redirect  # ← importante

urlpatterns = [
    path("admin/", admin.site.urls),

    path("accounts/logout/", logout_view, name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),

    path("rutas/", include(("rutas.urls", "rutas"), namespace="rutas")),
    path("servicios/", include(("servicios.urls", "servicios"), namespace="servicios")),
    path("cartera/", include(("cartera.urls", "cartera"), namespace="cartera")),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),

    path("post-login/", post_login_redirect, name="post_login"),  # ← usado por LOGIN_REDIRECT_URL

    path("", RedirectView.as_view(pattern_name="servicios:mis", permanent=False)),

    path("account/login/",  RedirectView.as_view(pattern_name="login",  permanent=False)),
    path("account/logout/", RedirectView.as_view(pattern_name="logout", permanent=False)),
]
