# servicios/utils.py
def concepto_pago_servicio(servicio):
    """
    Retorna un string tipo: 'Pago servicio – <Cliente> (<Origen> → <Destino>)'
    con caídas seguras si faltan campos.
    """
    # Cliente
    if hasattr(servicio, 'cliente') and servicio.cliente:
        cliente = getattr(servicio.cliente, 'nombre', None) or str(servicio.cliente)
    else:
        cliente = "Cliente sin nombre"

    # Trayecto (opcional)
    origen  = getattr(servicio, 'origen', None)
    destino = getattr(servicio, 'destino', None)
    trayecto = ""
    if origen or destino:
        trayecto = f" ({origen or '—'} → {destino or '—'})"

    return f"Pago servicio – {cliente}{trayecto}"
