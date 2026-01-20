# gastos/forms.py
from django import forms
from .models import Gasto

class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ['imagen', 'monto_total', 'fecha_emision', 'rut_emisor', 'folio']
        widgets = {
            'imagen': forms.FileInput(attrs={
                'class': 'form-control', 
                'accept': 'image/*,.pdf' 
            }),
            'fecha_emision': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control'}),
            'rut_emisor': forms.TextInput(attrs={'class': 'form-control'}),
            'folio': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
        labels = {
            'imagen': 'Foto de la Boleta (Evidencia)',
            'rut_emisor': 'RUT Proveedor',
            'fecha_emision': 'Fecha de Emisión',
        }

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def to_python(self, data):
        if not data:
            return None
        return data

    def clean(self, data, initial=None):
        if not data:
            raise forms.ValidationError("Es necesario seleccionar al menos un archivo.")
        return data

class CargaMasivaForm(forms.Form):
    imagenes = MultipleFileField(
        widget=MultipleFileInput(attrs={
            'multiple': True,
            'class': 'form-control',
            'accept': 'image/*,.pdf' 
        }),
        label="Selecciona boletas (Fotos o PDFs)"
    )