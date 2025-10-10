# cartera/queries.py
from django.db.models import Sum
from servicios.models import Servicio

def cartera_resumen(empresa):
    """
    Devuelve (total_pendiente_general, queryset_por_cliente)
    queryset_por_cliente = [{'cliente__id': int, 'cliente__nombre': str, 'total': Decimal}, ...]
    """
    qs = Servicio.objects.filter(ruta__empresa=empresa, estado_pago=Servicio.PENDIENTE)
    total = qs.aggregate(total=Sum('valor'))['total'] or 0
    por_cliente = (
        qs.values('cliente__id', 'cliente__nombre')
          .annotate(total=Sum('valor'))
          .order_by('-total')
    )
    return total, por_cliente

def cartera_por_cliente(empresa, cliente_id):
    """
    Servicios pendientes para un cliente dentro de la empresa actual.
    """
    return (Servicio.objects
            .filter(ruta__empresa=empresa, cliente_id=cliente_id, estado_pago=Servicio.PENDIENTE)
            .select_related('ruta', 'cliente')
            .order_by('-ruta__fecha', '-id'))
