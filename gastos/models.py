from django.db import models
from django.contrib.auth.models import User

class Empresa(models.Model):
    nombre = models.CharField(max_length=100)
    rut = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} - {self.empresa.nombre}"


    
class Obra(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Proyecto")
    ubicacion = models.CharField(max_length=200, blank=True, null=True, verbose_name="Ubicación/Dirección")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE) 
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Gasto(models.Model):
    CATEGORIAS = [
        ('MATERIALES', 'Materiales de Construcción'),
        ('MANO_OBRA', 'Mano de Obra / Tratos'),
        ('MAQUINARIA', 'Arriendo Maquinaria'),
        ('HERRAMIENTAS', 'Herramientas'),
        ('COMBUSTIBLE', 'Combustible'),
        ('TRANSPORTE', 'Fletes y Transporte'),
        ('ALIMENTACION', 'Alimentación'),
        ('EPP', 'Implementos de Seguridad (EPP)'),
        ('OFICINA', 'Gastos de Oficina'),
        ('OTROS', 'Otros Gastos'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    obra = models.ForeignKey(Obra, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Proyecto / Obra")
    
    imagen = models.FileField(upload_to='boletas/', verbose_name="Boleta o Factura")
    fecha_subida = models.DateTimeField(auto_now_add=True)

    rut_emisor = models.CharField(max_length=20, blank=True, null=True)
    folio = models.CharField(max_length=50, blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True)
    monto_total = models.IntegerField(default=0)

    procesado_exitosamente = models.BooleanField(default=False)
    nota_error = models.TextField(blank=True, null=True)

    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='MATERIALES',verbose_name="Categoría del Gasto")

    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción / Detalle")

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        return f"Gasto #{self.id} - ${self.monto_total}"    

class Presupuesto(models.Model):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='presupuestos')
    categoria = models.CharField(max_length=20, choices=Gasto.CATEGORIAS)
    monto = models.IntegerField(default=0, verbose_name="Monto Presupuestado")
    
    class Meta:
        unique_together = ('obra', 'categoria')

    def __str__(self):
        return f"{self.obra.nombre} - {self.get_categoria_display()}: ${self.monto}"