from threading import local
_state = local()

def set_current_empresa(empresa):
    _state.empresa = empresa

def get_current_empresa():
    return getattr(_state, 'empresa', None)

def empresa_context(request):
    return {'empresa_actual': get_current_empresa()}
