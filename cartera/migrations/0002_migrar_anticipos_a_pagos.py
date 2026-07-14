from django.db import migrations


def migrar_anticipos(apps, schema_editor):
    Servicio = apps.get_model("servicios", "Servicio")
    PagoServicio = apps.get_model("cartera", "PagoServicio")

    servicios = Servicio.objects.select_related("ruta", "cliente").filter(anticipo__gt=0)
    for servicio in servicios.iterator():
        if PagoServicio.objects.filter(servicio_id=servicio.id).exists():
            continue
        valor_servicio = int(servicio.valor or 0)
        valor_pago = min(int(servicio.anticipo or 0), valor_servicio)
        if valor_pago <= 0:
            continue
        PagoServicio.objects.create(
            empresa_id=servicio.ruta.empresa_id,
            servicio_id=servicio.id,
            cliente_id=servicio.cliente_id,
            ruta_id=servicio.ruta_id,
            valor=valor_pago,
            medio_pago="ANTICIPO",
            fecha_pago=servicio.ruta.fecha_salida,
            observacion="Pago migrado desde el anticipo historico del servicio.",
            impacta_caja=False,
        )
        if valor_servicio > 0 and valor_pago >= valor_servicio:
            estado = "PAG"
        elif valor_pago > 0:
            estado = "ANT"
        else:
            estado = "PEND"
        Servicio.objects.filter(pk=servicio.pk).update(anticipo=valor_pago, estado_pago=estado)


def no_op(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cartera", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrar_anticipos, no_op),
    ]
