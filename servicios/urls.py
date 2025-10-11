from django.urls import path
from . import views

app_name = 'servicios'
urlpatterns = [
    path('mis/', views.MisServiciosListView.as_view(), name='mis'),
    path('crear/', views.crear_servicio, name='crear'),
    path('ruta/<int:ruta_id>/', views.ServiciosPorRutaView.as_view(), name='por_ruta'),  # ⬅️ nuevo
    path('<int:pk>/', views.ServicioDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.editar_servicio, name='editar'),
    path('<int:pk>/eliminar/', views.eliminar_servicio, name='eliminar'),
    path('<int:pk>/pago-efectivo/', views.pago_efectivo_conductor, name='pago_efectivo'),
    path('<int:pk>/marcar-recogido/', views.marcar_recogido, name='marcar_recogido'),
    path('<int:pk>/marcar-entregado/', views.marcar_entregado, name='marcar_entregado'),
    path('<int:pk>/marcar-pagado-gerente/', views.marcar_pagado_gerente, name='marcar_pagado_gerente'),
    path('<int:pk>/comentar/', views.comentar_servicio, name='comentar'),
]
