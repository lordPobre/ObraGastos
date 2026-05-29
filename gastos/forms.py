from django import forms
from django.core.exceptions import ValidationError
from .models import Gasto, Obra

MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.pdf')


def validar_archivo(archivo):
    if archivo.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"El archivo '{archivo.name}' supera el tamaño máximo de {MAX_FILE_SIZE_MB} MB.")
    nombre = archivo.name.lower()
    if not any(nombre.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise ValidationError(f"Formato no soportado en '{archivo.name}'. Permitidos: {', '.join(ALLOWED_EXTENSIONS)}")


class GastoForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(user, 'perfil') and user.perfil.empresa:
            self.fields['obra'].queryset = Obra.objects.filter(empresa=user.perfil.empresa, activo=True)
        else:
            self.fields['obra'].queryset = Obra.objects.none()
        self.fields['monto_neto'].required = False
        self.fields['iva'].required = False
        self.fields['nombre_emisor'].required = False
        self.fields['tipo_documento'].required = False

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

    def clean(self):
        cleaned = super().clean()
        monto_neto  = cleaned.get('monto_neto') or 0
        iva         = cleaned.get('iva') or 0
        monto_total = cleaned.get('monto_total') or 0
        tiene_iva   = cleaned.get('tiene_iva', True)

        # Si ingresaron neto pero no total → calcular total
        if monto_neto > 0 and monto_total == 0:
            if tiene_iva:
                cleaned['iva']         = round(monto_neto * 0.19)
                cleaned['monto_total'] = monto_neto + cleaned['iva']
            else:
                cleaned['iva']         = 0
                cleaned['monto_total'] = monto_neto

        # Si ingresaron total pero no neto → calcular neto
        elif monto_total > 0 and monto_neto == 0:
            if tiene_iva:
                cleaned['monto_neto'] = round(monto_total / 1.19)
                cleaned['iva']        = monto_total - cleaned['monto_neto']
            else:
                cleaned['monto_neto'] = monto_total
                cleaned['iva']        = 0

        return cleaned

    class Meta:
        model = Gasto
        fields = [
            'imagen', 'tipo_documento',
            'monto_neto', 'iva', 'monto_total', 'tiene_iva',
            'fecha_emision', 'rut_emisor', 'nombre_emisor',
            'folio', 'categoria', 'obra', 'descripcion',
        ]
        widgets = {
            'imagen':         forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'fecha_emision':  forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'monto_neto':     forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'iva':            forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'monto_total':    forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'tiene_iva':      forms.CheckboxInput(),
            'tipo_documento': forms.Select(attrs={'class': 'form-select'}),
            'rut_emisor':     forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_emisor':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del proveedor'}),
            'obra':           forms.Select(attrs={'class': 'form-select fw-bold'}),
            'folio':          forms.TextInput(attrs={'class': 'form-control'}),
            'categoria':      forms.Select(attrs={'class': 'form-select fw-bold'}),
            'descripcion':    forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'imagen':         'Foto de la Boleta (Evidencia)',
            'rut_emisor':     'RUT Proveedor',
            'nombre_emisor':  'Nombre Proveedor',
            'fecha_emision':  'Fecha de Emisión',
            'monto_neto':     'Monto Neto (sin IVA)',
            'iva':            'IVA (19%)',
            'monto_total':    'Monto Total (con IVA)',
            'tiene_iva':      '¿Afecto a IVA?',
            'tipo_documento': 'Tipo de documento',
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
            'nombre':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Edificio Centro'}),
            'ubicacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. Principal 123'}),
            'activo':    forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CargaMasivaForm(forms.Form):
    imagenes = MultipleFileField(
        widget=MultipleFileInput(attrs={'multiple': True, 'class': 'form-control', 'accept': 'image/*,.pdf'}),
        label="Selecciona boletas (Fotos o PDFs)"
    )

    def clean_imagenes(self):
        from django.core.files.uploadedfile import UploadedFile
        archivos = self.files.getlist('imagenes')
        if not archivos:
            raise ValidationError("Debes seleccionar al menos un archivo.")
        for f in archivos:
            if isinstance(f, UploadedFile):
                validar_archivo(f)
        return archivos