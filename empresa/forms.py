# empresa/forms.py
from django import forms
from .models import Cliente

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "contacto", "telefono", "direccion", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Empresa o persona"
            }),
            "contacto": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Nombre del contacto"
            }),
            "telefono": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Teléfono"
            }),
            "direccion": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Dirección"
            }),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
