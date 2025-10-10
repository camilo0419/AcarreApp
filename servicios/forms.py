from django import forms
from .models import Servicio, ServicioComentario

class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Placeholders útiles
        self.fields['origen'].widget.attrs.update({
            'placeholder': 'Bodega Calle 10 #25-30, Medellín',
        })
        self.fields['destino'].widget.attrs.update({
            'placeholder': 'Cra 43A #7-50, El Poblado',
        })

        # Numéricos con buen UX
        for f in ('valor', 'anticipo'):
            if f in self.fields:
                self.fields[f].widget.attrs.update({
                    'min': 0,
                    'step': 1,
                    'inputmode': 'numeric',
                    'pattern': r'\d*',
                })

class ServicioComentarioForm(forms.ModelForm):
    class Meta:
        model = ServicioComentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Escribe un comentario...'}),
        }