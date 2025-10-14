# servicios/urls.py
from django.urls import path
from . import views

app_name = "servicios"

urlpatterns = [
    # Lista canónica (por ruta)
    path("por-ruta/<int:ruta_id>/", views.ServiciosPorRutaView.as_view(), name="por_ruta"),

    # Detalle / CRUD
    path("<int:pk>/", views.ServicioDetailView.as_view(), name="detail"),
    path("crear/", views.crear_servicio, name="crear"),
    path("<int:pk>/editar/", views.editar_servicio, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar_servicio, name="eliminar"),

    # Acciones de estado
    path("<int:pk>/marcar-recogido/", views.marcar_recogido, name="marcar_recogido"),
    path("<int:pk>/marcar-entregado/", views.marcar_entregado, name="marcar_entregado"),
    path("<int:pk>/marcar-pagado/", views.marcar_pagado_gerente, name="marcar_pagado_gerente"),

    # Pagos (nombre oficial + alias para compatibilidad)
    path("<int:pk>/pago-efectivo/", views.pago_efectivo_conductor, name="pago_efectivo_conductor"),
    path("<int:pk>/pago-efectivo/", views.pago_efectivo_conductor, name="pago_efectivo"),

    # Comentarios
    path("<int:pk>/comentar/", views.comentar_servicio, name="comentar"),
]
