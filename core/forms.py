from django import forms
from .models import Product, Cliente, Abono


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Eliminado 'sale_price' pues ya no existe en el modelo
        fields = ["reference", "description", "purchase_price", "stock"]
        widgets = {
            "reference": forms.TextInput(
                attrs={
                    "class": "w-full bg-gray-700 text-white rounded px-3 py-2",
                    "placeholder": "Referencia",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "w-full bg-gray-700 text-white rounded px-3 py-2",
                    "placeholder": "Descripción del producto",
                }
            ),
            "purchase_price": forms.NumberInput(
                attrs={
                    "class": "w-full bg-gray-700 text-white rounded px-3 py-2",
                    "step": "0.01",
                    "placeholder": "Precio de compra",
                }
            ),
            "stock": forms.NumberInput(
                attrs={
                    "class": "w-full bg-gray-700 text-white rounded px-3 py-2",
                    "placeholder": "Stock",
                }
            ),
        }


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        exclude = ["creado_por"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-input"}),
            "cedula": forms.TextInput(attrs={"class": "form-input"}),
            "telefono": forms.TextInput(attrs={"class": "form-input"}),
            "ciudad": forms.TextInput(attrs={"class": "form-input"}),
            "direccion": forms.TextInput(attrs={"class": "form-input"}),
            "correo": forms.EmailInput(attrs={"class": "form-input"}),
            "estado": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class AbonoForm(forms.ModelForm):
    class Meta:
        model = Abono
        fields = ["venta", "monto"]
        widgets = {
            "venta": forms.Select(
                attrs={"class": "w-full px-3 py-2 rounded bg-gray-700 text-white"}
            ),
            "monto": forms.NumberInput(
                attrs={"class": "w-full px-3 py-2 rounded bg-gray-700 text-white"}
            ),
        }
