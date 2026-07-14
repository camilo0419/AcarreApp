from django import forms

from cartera.models import PagoServicio

from .models import Servicio, ServicioComentario


class ServicioForm(forms.ModelForm):
    pago_inicial = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Pago inicial",
        widget=forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric", "pattern": r"\d*"}),
    )
    medio_pago_inicial = forms.ChoiceField(
        choices=[choice for choice in PagoServicio.MEDIOS if choice[0] != PagoServicio.MEDIO_ANTICIPO],
        required=False,
        initial=PagoServicio.MEDIO_EFECTIVO,
        label="Medio del pago inicial",
    )

    class Meta:
        model = Servicio
        fields = [
            "ruta",
            "cliente",
            "valor",
            "cantidad",
            "origen",
            "destino",
            "notas",
            "pago_inicial",
            "medio_pago_inicial",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in ("valor", "pago_inicial"):
            self.fields[field_name].required = False
            self.fields[field_name].widget.attrs.update(
                {
                    "min": 0,
                    "step": 1,
                    "inputmode": "numeric",
                    "pattern": r"\d*",
                }
            )

        self.fields["cantidad"].widget.attrs.update(
            {
                "min": 1,
                "step": 1,
                "inputmode": "numeric",
                "pattern": r"\d*",
            }
        )
        if self.fields["cantidad"].initial in (None, "") and getattr(self.instance, "cantidad", None) in (None, 0):
            self.fields["cantidad"].initial = 1

        self.fields["origen"].widget.attrs.update({"placeholder": "Bodega Calle 10 #25-30, Medellin"})
        self.fields["destino"].widget.attrs.update({"placeholder": "Cra 43A #7-50, El Poblado"})

        if self.instance and self.instance.pk:
            self.fields["pago_inicial"].disabled = True
            self.fields["medio_pago_inicial"].disabled = True
            self.fields["pago_inicial"].help_text = "Los pagos se registran desde cartera o el detalle del servicio."

    def clean_valor(self):
        value = self.cleaned_data.get("valor")
        return 0 if value in (None, "") else value

    def clean_pago_inicial(self):
        value = self.cleaned_data.get("pago_inicial")
        return 0 if value in (None, "") else value

    def clean(self):
        cleaned = super().clean()
        valor = cleaned.get("valor") or 0
        pago_inicial = cleaned.get("pago_inicial") or 0
        if self.instance and self.instance.pk:
            cleaned["pago_inicial"] = 0
            return cleaned
        if pago_inicial > valor:
            self.add_error("pago_inicial", "El pago inicial no puede superar el valor del servicio.")
        return cleaned


class ServicioComentarioForm(forms.ModelForm):
    class Meta:
        model = ServicioComentario
        fields = ["texto"]
        widgets = {
            "texto": forms.Textarea(attrs={"rows": 2, "placeholder": "Escribe un comentario..."}),
        }
