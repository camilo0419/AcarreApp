# cartera/views.py
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from empresa.models import Cliente  # ← TU modelo real
from . import queries

@login_required
def pendientes(request):
    # La empresa debe venir del middleware/contexto que ya tienes
    empresa = getattr(request, 'empresa_actual', None)
    if empresa is None:
        raise Http404("No hay empresa activa en el contexto.")

    total, por_cliente = queries.cartera_resumen(empresa)
    contexto = {
        'empresa': empresa,
        'total_general': total,
        'por_cliente': por_cliente,
    }
    return render(request, 'cartera/pendientes.html', contexto)

@login_required
def cliente_detalle(request, cliente_id: int):
    empresa = getattr(request, 'empresa_actual', None)
    if empresa is None:
        raise Http404("No hay empresa activa en el contexto.")

    # Aseguramos que el cliente pertenezca a la misma empresa
    cliente = get_object_or_404(Cliente, id=cliente_id, empresa=empresa)

    servicios = queries.cartera_por_cliente(empresa, cliente_id)
    total_cliente = sum((s.valor for s in servicios), Decimal('0'))

    contexto = {
        'empresa': empresa,
        'cliente': cliente,
        'servicios': servicios,
        'total_cliente': total_cliente,
    }
    return render(request, 'cartera/cliente_detalle.html', contexto)
