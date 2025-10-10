# dashboard/urls.py
from django.urls import path
from .views import HomeGerenteView

app_name = "dashboard"

urlpatterns = [
    path("", HomeGerenteView.as_view(), name="index"),          # alias → evita NoReverseMatch
    path("gerente/", HomeGerenteView.as_view(), name="home_gerente"),
]
