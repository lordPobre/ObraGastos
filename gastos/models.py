from django.db import models
from django.contrib.auth.models import User

# 1. Nuevo Modelo para las Obras
class Obra(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    activo = models.BooleanField(default=True) # Para ocultar obras terminadas

    def __str__(self):
        return self.nombre

class Gasto(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    # 2. Conectamos el Gasto a la Obra (null=True permite que existan gastos sin obra asignada por ahora)
    obra = models.ForeignKey(Obra, on_delete=models.SET_NULL, null=True, blank=True)
    
    imagen = models.FileField(upload_to='boletas/', verbose_name="Boleta o Factura")
    fecha_subida = models.DateTimeField(auto_now_add=True)
    
    rut_emisor = models.CharField(max_length=20, blank=True, null=True)
    folio = models.CharField(max_length=50, blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True)
    monto_total = models.IntegerField(default=0)
    
    procesado_exitosamente = models.BooleanField(default=False)
    nota_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Gasto #{self.id} - ${self.monto_total}"