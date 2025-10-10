from django import forms
from django.contrib.auth.models import User
from .models import Ruta
from empresa.models import Vehiculo
from usuarios.models import UserProfile
from acarreapp.tenancy import get_current_empresa

class RutaForm(forms.ModelForm):
    class Meta:
        model = Ruta
        fields = ['nombre', 'fecha_salida', 'vehiculo', 'conductor', 'base_efectivo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        emp = get_current_empresa()
        self.fields['vehiculo'].queryset = Vehiculo.objects.filter(empresa=emp, activo=True)
        conductores_ids = UserProfile.objects.filter(
            empresa=emp, rol='CONDUCTOR'
        ).values_list('user_id', flat=True)
        self.fields['conductor'].queryset = User.objects.filter(id__in=conductores_ids)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.empresa = get_current_empresa()
        if commit:
            obj.save()
        return obj
    
    def clean(self):
        cleaned = super().clean()
        from acarreapp.tenancy import get_current_empresa
        from .models import Ruta
        emp = get_current_empresa()
        conductor = cleaned.get('conductor')
        estado = self.instance.estado if self.instance.pk else 'ACTIVA'
        if conductor and estado == 'ACTIVA':
            qs = Ruta.objects.filter(empresa=emp, conductor=conductor, estado='ACTIVA')
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                from django.core.exceptions import ValidationError
                raise ValidationError({'conductor': 'Este conductor ya tiene una ruta ACTIVA. Debe cerrarla antes de asignarle otra.'})
        return cleaned

