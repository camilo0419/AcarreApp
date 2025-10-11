from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("operacion/", views.OperacionView.as_view(), name="operacion"),
    path("cartera/", views.CarteraView.as_view(), name="cartera"),

    # APIs para mini-mapas
    path("api/rutas-activas-lite/", views.RutasActivasLiteAPI.as_view(), name="api_rutas_activas_lite"),
    path("api/ruta/<int:pk>/points/", views.RutaPointsAPI.as_view(), name="api_ruta_points"),

    # Vista de recorrido (detalle simple con mapa)
    path("ruta/<int:pk>/recorrido/", views.RutaRecorridoView.as_view(), name="ruta_recorrido"),
]
