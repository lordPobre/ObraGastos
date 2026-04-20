# gastos/forms.py
from django import forms
from .models import Gasto,Obra

class GastoForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si el usuario tiene empresa, filtramos las obras
        if hasattr(user, 'perfil') and user.perfil.empresa:
            self.fields['obra'].queryset = Obra.objects.filter(empresa=user.perfil.empresa, activo=True)
        else:
            self.fields['obra'].queryset = Obra.objects.none()

    class Meta:
        model = Gasto
        fields = ['imagen', 'monto_total', 'fecha_emision', 'rut_emisor', 'folio', 'categoria', 'obra', 'descripcion']
        widgets = {
            'imagen': forms.FileInput(attrs={
                'class': 'form-control', 
                'accept': 'image/*,.pdf' 
            }),
            'fecha_emision': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control'}),
            'rut_emisor': forms.TextInput(attrs={'class': 'form-control'}),
            'obra': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'folio': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select fw-bold'}),
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
        # Importante: Devolvemos la data tal cual para que la vista use getlist()
        return data

    def clean(self, data, initial=None):
        # Evitamos la validación estándar que espera un solo archivo
        if not data:
            raise forms.ValidationError("Es necesario seleccionar al menos un archivo.")
        return data
    
class ObraForm(forms.ModelForm):
    class Meta:
        model = Obra
        fields = ['nombre', 'ubicacion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Edificio Centro'}),
            'ubicacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. Principal 123'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
# --- TU FORMULARIO DE CARGA ---

class CargaMasivaForm(forms.Form):
    imagenes = MultipleFileField(
        widget=MultipleFileInput(attrs={
            'multiple': True,
            'class': 'form-control',
            # AQUÍ ESTÁ EL CAMBIO: Agregamos .pdf
            'accept': 'image/*,.pdf' 
        }),
        label="Selecciona boletas (Fotos o PDFs)"
    )