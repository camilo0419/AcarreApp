from django.urls import path
from .views import RutaDetailView, ReordenarServiciosView
from . import views

app_name = 'rutas'
urlpatterns = [
    path('', views.RutasListView.as_view(), name='list'),
    path('crear/', views.crear_ruta, name='crear'),

    # Detalle (dos nombres válidos: 'detail' y 'hoja')
    path("<int:pk>/", RutaDetailView.as_view(), name="detail"),
    path("<int:pk>/hoja/", RutaDetailView.as_view(), name="hoja"),

    # Drag & drop
    path("<int:ruta_id>/reordenar/", ReordenarServiciosView.as_view(), name="reordenar_servicios"),

    path('<int:pk>/cerrar/', views.cerrar_ruta_view, name='cerrar'),
    path('<int:pk>/borrar/', views.borrar_ruta, name='borrar'),
    path('<int:pk>/gasto/', views.agregar_gasto, name='gasto'),
    path('<int:pk>/ingreso/', views.agregar_ingreso_extra, name='ingreso'),

    path('<int:ruta_id>/cierre/', views.cierre_resumen, name='cierre_resumen'),
    path('<int:ruta_id>/cierre/csv/', views.exportar_cierre_csv, name='exportar_cierre_csv'),
    path('<int:ruta_id>/recorrido/', views.recorrido_ruta_view, name='recorrido'),
    path("<int:ruta_id>/cierre/exportar-xlsx/", views.exportar_cierre_xlsx, name="exportar_cierre_xlsx"),
]
