from django.contrib import admin
from .models import Gasto
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Gasto, Empresa, PerfilUsuario

class PerfilInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False

class UserAdmin(BaseUserAdmin):
    inlines = (PerfilInline,)

class GastoAdmin(admin.ModelAdmin):
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

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(Gasto)
admin.site.register(Empresa)
admin.site.register(PerfilUsuario)

