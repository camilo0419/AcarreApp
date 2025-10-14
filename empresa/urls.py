# empresa/urls.py
from django.urls import path
from .views import (
    ClienteListView, ClienteDetailView,
    ClienteCreateView, ClienteUpdateView, ClienteDeleteView
)

app_name = "empresa"

urlpatterns = [
    path("clientes/", ClienteListView.as_view(), name="clientes_list"),
    path("clientes/nuevo/", ClienteCreateView.as_view(), name="clientes_create"),
    path("clientes/<int:pk>/", ClienteDetailView.as_view(), name="clientes_detail"),
    path("clientes/<int:pk>/editar/", ClienteUpdateView.as_view(), name="clientes_update"),
    path("clientes/<int:pk>/eliminar/", ClienteDeleteView.as_view(), name="clientes_delete"),
]
