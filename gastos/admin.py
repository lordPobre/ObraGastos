from django.contrib import admin
from .models import Gasto
from django.utils.html import format_html

@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    # Columnas que se verán en la tabla
    list_display = ('id', 'usuario', 'mostrar_monto', 'fecha_emision', 'procesado_exitosamente', 'ver_imagen')
    list_filter = ('procesado_exitosamente', 'fecha_subida')
    search_fields = ('rut_emisor', 'folio')
    readonly_fields = ('fecha_subida',)

    def mostrar_monto(self, obj):
        # Formato chileno de pesos
        return f"${obj.monto_total:,.0f}".replace(",", ".")
    mostrar_monto.short_description = "Monto Total"

    def ver_imagen(self, obj):
        if obj.imagen:
            return format_html('<a href="{}" target="_blank">Ver Boleta</a>', obj.imagen.url)
        return "-"
    ver_imagen.short_description = "Archivo"