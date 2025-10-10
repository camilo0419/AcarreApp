from django import forms
from .models import Servicio, ServicioComentario

class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio
        fields = "__all__"  # tus fields como los tengas

    def clean(self):
        cleaned = super().clean()
        ruta = cleaned.get('ruta') or getattr(self.instance, 'ruta', None)
        if ruta and getattr(ruta, 'estado', None) != 'ACTIVA':
            from django.core.exceptions import ValidationError
            raise ValidationError({'ruta': 'No se pueden agregar/editar servicios en una ruta CERRADA.'})
        return cleaned

class ServicioComentarioForm(forms.ModelForm):
    class Meta:
        model = ServicioComentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Escribe un comentario...'}),
        }