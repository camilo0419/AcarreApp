# cartera/urls.py
from django.urls import path
from . import views

app_name = "cartera"

urlpatterns = [
    path('pendientes/', views.pendientes, name='pendientes'),
    path('cliente/<int:cliente_id>/', views.cliente_detalle, name='cliente_detalle'),
]
