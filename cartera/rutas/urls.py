from django.urls import path
from . import views

app_name = 'rutas'
urlpatterns = [
    path('', views.RutasListView.as_view(), name='list'),
    path('crear/', views.crear_ruta, name='crear'),
    path('<int:pk>/hoja/', views.RutaDetailView.as_view(), name='hoja'),   # ⬅️ hoja de ruta
    path('<int:pk>/cerrar/', views.cerrar_ruta_view, name='cerrar'),
    path('<int:pk>/borrar/', views.borrar_ruta, name='borrar'),
    path('<int:pk>/gasto/', views.agregar_gasto, name='gasto'),
    path('<int:pk>/ingreso/', views.agregar_ingreso_extra, name='ingreso'),

    path('<int:ruta_id>/cierre/', views.cierre_resumen, name='cierre_resumen'),
    path('<int:ruta_id>/cierre/csv/', views.exportar_cierre_csv, name='exportar_cierre_csv'),
]
