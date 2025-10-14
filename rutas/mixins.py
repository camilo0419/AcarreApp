# rutas/mixins.py
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

def _es_gerente(user) -> bool:
    # is_staff siempre habilita (superuser/staff)
    if not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    # Intenta leer el rol desde el perfil (usuarios.UserProfile) o directamente en el user
    rol = (
        getattr(getattr(user, "userprofile", None), "rol", None)
        or getattr(user, "rol", None)
        or ""
    )
    return str(rol).upper() == "GERENTE"

class GerenteRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _es_gerente(self.request.user)
