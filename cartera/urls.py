from django.urls import path

from . import views

app_name = "cartera"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clientes/", views.clientes_list, name="clientes_list"),
    path("clientes/<int:cliente_id>/", views.cliente_detalle, name="cliente_detalle"),
    path("clientes/<int:cliente_id>/estado-cuenta.pdf", views.estado_cuenta_pdf, name="estado_cuenta_pdf"),
    path("servicios/", views.servicios_list, name="servicios_list"),
    path("servicios/<int:servicio_id>/pagar/", views.registrar_pago, name="registrar_pago"),
    path("servicios/<int:servicio_id>/cuenta-cobro.pdf", views.cuenta_cobro_pdf, name="cuenta_cobro_pdf"),
    path("pagos/", views.pagos_list, name="pagos_list"),
    path("pagos/<int:pago_id>/anular/", views.anular_pago, name="anular_pago"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("pendientes/", views.pendientes, name="pendientes"),
    path("cliente/<int:cliente_id>/", views.cliente_detalle, name="cliente_detalle_legacy"),
]
