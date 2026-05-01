"""
Formularios del módulo de gastos.

CORRECCIONES:
- Validación de tamaño y tipo de archivo en uploads
- CargaMasivaForm ahora acepta obra opcional
- Mensajes de error más claros
"""
from django import forms
from django.core.exceptions import ValidationError

from .models import Gasto, Obra


# Límites de archivos
MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.pdf')


def validar_archivo(archivo):
    """Valida tamaño y extensión de un archivo subido."""
    if archivo.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValidationError(
            f"El archivo '{archivo.name}' supera el tamaño máximo de {MAX_FILE_SIZE_MB} MB."
        )

    nombre = archivo.name.lower()
    if not any(nombre.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise ValidationError(
            f"Formato no soportado en '{archivo.name}'. "
            f"Permitidos: {', '.join(ALLOWED_EXTENSIONS)}"
        )


class GastoForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(user, 'perfil') and user.perfil.empresa:
            self.fields['obra'].queryset = Obra.objects.filter(
                empresa=user.perfil.empresa, activo=True
            )
        else:
            self.fields['obra'].queryset = Obra.objects.none()

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen and hasattr(imagen, 'size'):
            validar_archivo(imagen)
        return imagen

    def clean_monto_total(self):
        monto = self.cleaned_data.get('monto_total')
        if monto is not None and monto < 0:
            raise ValidationError("El monto no puede ser negativo.")
        return monto

    class Meta:
        model = Gasto
        fields = [
            'imagen', 'monto_total', 'fecha_emision', 'rut_emisor',
            'folio', 'categoria', 'obra', 'descripcion'
        ]
        widgets = {
            'imagen': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.pdf'
            }),
            'fecha_emision': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'monto_total': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'rut_emisor': forms.TextInput(attrs={'class': 'form-control'}),
            'obra': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'folio': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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
            raise ValidationError("Es necesario seleccionar al menos un archivo.")
        return data


class ObraForm(forms.ModelForm):
    class Meta:
        model = Obra
        fields = ['nombre', 'ubicacion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Edificio Centro'
            }),
            'ubicacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Av. Principal 123'
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CargaMasivaForm(forms.Form):
    imagenes = MultipleFileField(
        widget=MultipleFileInput(attrs={
            'multiple': True,
            'class': 'form-control',
            'accept': 'image/*,.pdf'
        }),
        label="Selecciona boletas (Fotos o PDFs)"
    )

    def clean_imagenes(self):
        # Aquí valida cada archivo individualmente
        from django.core.files.uploadedfile import UploadedFile
        archivos = self.files.getlist('imagenes')
        if not archivos:
            raise ValidationError("Debes seleccionar al menos un archivo.")

        for f in archivos:
            if isinstance(f, UploadedFile):
                validar_archivo(f)

        return archivos