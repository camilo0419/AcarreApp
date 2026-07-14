from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import CarteraEmpresaConfig, CuentaCobro, PagoServicio


class PagoServicioForm(forms.Form):
    valor = forms.IntegerField(min_value=1, label="Valor recibido")
    medio_pago = forms.ChoiceField(
        choices=[choice for choice in PagoServicio.MEDIOS if choice[0] != PagoServicio.MEDIO_ANTICIPO],
        label="Medio de pago",
    )
    fecha_pago = forms.DateField(
        label="Fecha de pago",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    referencia = forms.CharField(max_length=120, required=False, label="Referencia")
    observacion = forms.CharField(
        required=False,
        label="Observacion",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, saldo=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.saldo = int(saldo or 0)
        self.fields["valor"].widget.attrs.update(
            {"min": 1, "max": self.saldo, "step": 1, "inputmode": "numeric"}
        )
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if self.saldo <= 0:
            raise ValidationError("Este servicio no tiene saldo pendiente.")
        if valor > self.saldo:
            raise ValidationError("El pago no puede superar el saldo pendiente.")
        return valor


class AnularPagoForm(forms.Form):
    motivo = forms.CharField(
        max_length=240,
        label="Motivo de anulacion",
        widget=forms.Textarea(attrs={"rows": 2, "class": "input"}),
    )


class CarteraEmpresaConfigForm(forms.ModelForm):
    class Meta:
        model = CarteraEmpresaConfig
        fields = [
            "nombre_emisor",
            "nit_emisor",
            "direccion_emisor",
            "telefono_emisor",
            "email_emisor",
            "logo_static_path",
            "prefijo_cuenta_cobro",
            "proximo_consecutivo",
            "notas_estado_cuenta",
            "notas_cuenta_cobro",
        ]
        widgets = {
            "notas_estado_cuenta": forms.Textarea(attrs={"rows": 3}),
            "notas_cuenta_cobro": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()

    def clean_prefijo_cuenta_cobro(self):
        prefijo = (self.cleaned_data.get("prefijo_cuenta_cobro") or "CC").strip().upper()
        if not prefijo.replace("-", "").isalnum():
            raise ValidationError("Usa solo letras, numeros o guion en el prefijo.")
        return prefijo

    def clean_proximo_consecutivo(self):
        proximo = self.cleaned_data["proximo_consecutivo"]
        if self.empresa:
            ultimo = (
                CuentaCobro.objects.filter(empresa=self.empresa)
                .order_by("-consecutivo")
                .values_list("consecutivo", flat=True)
                .first()
            )
            if ultimo and proximo <= ultimo:
                raise ValidationError(f"Debe ser mayor que el ultimo consecutivo usado ({ultimo}).")
        return proximo
