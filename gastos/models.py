from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from cloudinary.models import CloudinaryField


class Empresa(models.Model):
    nombre = models.CharField(max_length=100)
    rut = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self):
        return f"{self.user.username} - {self.empresa.nombre}"


class Obra(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Proyecto")
    ubicacion = models.CharField(max_length=200, blank=True, null=True, verbose_name="Ubicación/Dirección")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, db_index=True)
    activo = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-activo', 'nombre']
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        indexes = [
            models.Index(fields=['empresa', 'activo']),
        ]

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

    # CORRECCIÓN: SET_NULL para mantener histórico contable si se borra el usuario
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos'
    )

    obra = models.ForeignKey(
        Obra,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Proyecto / Obra",
        db_index=True
    )

    imagen = CloudinaryField('boleta',resource_type='auto',blank=True,null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    rut_emisor = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    folio = models.CharField(max_length=50, blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True, db_index=True)
    monto_total = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    procesado_exitosamente = models.BooleanField(default=False)
    nota_error = models.TextField(blank=True, null=True)

    # NUEVO: Validación SII
    validado_sii = models.BooleanField(default=False, verbose_name="Validado por SII")

    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIAS,
        default='MATERIALES',
        verbose_name="Categoría del Gasto",
        db_index=True
    )

    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción / Detalle")

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True
    )

    class Meta:
        ordering = ['-fecha_emision', '-id']
        verbose_name = "Gasto"
        verbose_name_plural = "Gastos"
        indexes = [
            models.Index(fields=['empresa', '-fecha_emision']),
            models.Index(fields=['obra', '-fecha_emision']),
            models.Index(fields=['empresa', 'categoria']),
        ]

    def __str__(self):
        return f"Gasto #{self.id} - ${self.monto_total}"

    @property
    def estado(self):
        """Retorna el estado del gasto para mostrar en UI."""
        if not self.monto_total or self.monto_total == 0:
            return 'pendiente'
        if not self.rut_emisor:
            return 'incompleto'
        if self.validado_sii:
            return 'validado_sii'
        return 'completo'


class Presupuesto(models.Model):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='presupuestos')
    categoria = models.CharField(max_length=20, choices=Gasto.CATEGORIAS)
    monto = models.IntegerField(
        default=0,
        verbose_name="Monto Presupuestado",
        validators=[MinValueValidator(0)]
    )

    class Meta:
        unique_together = ('obra', 'categoria')
        verbose_name = "Presupuesto"
        verbose_name_plural = "Presupuestos"

    def __str__(self):
        return f"{self.obra.nombre} - {self.get_categoria_display()}: ${self.monto}"
