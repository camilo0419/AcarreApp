from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from .tenancy import set_current_empresa
from empresa.models import Empresa

class EmpresaActualMiddleware(MiddlewareMixin):
    def process_request(self, request):
        slug = None

        # 1) Si el usuario está logueado y tiene perfil, usar su empresa
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            profile = getattr(user, "userprofile", None)
            if profile and profile.empresa and profile.empresa.activa:
                set_current_empresa(profile.empresa)
                return

        # 2) Si no hay usuario/empresa, usar subdominio (producción) o DEFAULT_EMPRESA_SLUG (dev)
        slug = request.session.get('empresa_slug') or getattr(settings, 'DEFAULT_EMPRESA_SLUG', None)

        host = request.get_host().split(':')[0]
        if host.count('.') >= 2:  # subdominio presente
            possible = host.split('.')[0]
            slug = possible or slug

        empresa = None
        if slug:
            empresa = Empresa.objects.filter(slug=slug, activa=True).first()
        if not empresa:
            empresa = Empresa.objects.filter(activa=True).first()

        set_current_empresa(empresa)
