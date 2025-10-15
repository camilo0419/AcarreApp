from django import forms
from .models import Servicio, ServicioComentario

class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio
        exclude = ['orden']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 👇 ACEPTAR CERO y no exigir obligatorios
        for f in ('valor', 'anticipo'):
            if f in self.fields:
                self.fields[f].required = False
                self.fields[f].widget.attrs.update({
                    'min': 0,
                    'step': 1,
                    'inputmode': 'numeric',
                    'pattern': r'\d*',
                })

        # 👇 NUEVO: Cantidad con mínimo 1
        if 'cantidad' in self.fields:
            self.fields['cantidad'].widget.attrs.update({
                'min': 1,
                'step': 1,
                'inputmode': 'numeric',
                'pattern': r'\d*',
            })
            if self.fields['cantidad'].initial in (None, '') and getattr(self.instance, 'cantidad', None) in (None, 0):
                self.fields['cantidad'].initial = 1

        # Placeholders útiles
        if 'origen' in self.fields:
            self.fields['origen'].widget.attrs.update({
                'placeholder': 'Bodega Calle 10 #25-30, Medellín',
            })
        if 'destino' in self.fields:
            self.fields['destino'].widget.attrs.update({
                'placeholder': 'Cra 43A #7-50, El Poblado',
            })

        # Estado de pago por defecto
        if 'estado_pago' in self.fields and not self.fields['estado_pago'].initial:
            self.fields['estado_pago'].initial = 'PEND'

    # 👇 Normaliza vacío -> 0
    def clean_valor(self):
        v = self.cleaned_data.get('valor')
        return 0 if v in (None, '') else v

    def clean_anticipo(self):
        a = self.cleaned_data.get('anticipo')
        a = 0 if a in (None, '') else a
        # Validación básica con el valor ya normalizado
        valor = self.cleaned_data.get('valor')
        valor = 0 if valor in (None, '') else valor
        if a < 0:
            raise forms.ValidationError("El anticipo no puede ser negativo.")
        if a > valor:
            # Permitimos que el view lo sincronice si el estado es PAG, pero acá prevenimos errores
            raise forms.ValidationError("El anticipo no puede superar el valor del servicio.")
        return a

    def clean(self):
        cleaned = super().clean()
        valor = cleaned.get('valor') or 0
        anticipo = cleaned.get('anticipo') or 0
        estado = cleaned.get('estado_pago')

        # Coherencia básica por estado (sin romper si el usuario cambia luego)
        if estado == 'PEND':
            cleaned['anticipo'] = 0
        elif estado == 'PAG':
            cleaned['anticipo'] = valor
        else:  # 'ANT'
            if anticipo <= 0:
                self.add_error('anticipo', "Para ANTICIPO debes ingresar un valor mayor a 0.")
            if anticipo > valor:
                self.add_error('anticipo', "El anticipo no puede superar el valor del servicio.")

        return cleaned


class ServicioComentarioForm(forms.ModelForm):
    class Meta:
        model = ServicioComentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Escribe un comentario...'}),
        }
