from django.contrib import admin

from .models import CarteraEmpresaConfig, CuentaCobro, PagoServicio


@admin.register(CarteraEmpresaConfig)
class CarteraEmpresaConfigAdmin(admin.ModelAdmin):
    list_display = ("empresa", "prefijo_cuenta_cobro", "proximo_consecutivo", "actualizado_en")
    search_fields = ("empresa__nombre", "nombre_emisor", "nit_emisor")


@admin.register(PagoServicio)
class PagoServicioAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "empresa",
        "servicio",
        "cliente",
        "valor",
        "medio_pago",
        "fecha_pago",
        "impacta_caja",
        "anulado",
    )
    list_filter = ("empresa", "medio_pago", "impacta_caja", "anulado", "fecha_pago")
    search_fields = ("servicio__id", "cliente__nombre", "referencia")
    raw_id_fields = ("servicio", "cliente", "ruta", "movimiento_caja", "movimiento_reversion")


@admin.register(CuentaCobro)
class CuentaCobroAdmin(admin.ModelAdmin):
    list_display = ("numero", "empresa", "servicio", "cliente", "emitida_en")
    list_filter = ("empresa", "emitida_en")
    search_fields = ("numero", "cliente__nombre", "servicio__id")
    raw_id_fields = ("servicio", "cliente")
