from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
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
    ubicacion = models.CharField(max_length=200, blank=True, null=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, db_index=True)
    activo = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-activo', 'nombre']
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        indexes = [models.Index(fields=['empresa', 'activo'])]
    def __str__(self):
        return self.nombre


class Gasto(models.Model):
    CATEGORIAS = [
        ('MATERIALES',    'Materiales de Construcción'),
        ('MO_CONTRATA',   'Mano de Obra · Contrata'),
        ('MO_SUBCONTRATA','Mano de Obra · Subcontrata'),
        ('MO_JORNAL',     'Mano de Obra · Jornal / Día'),
        ('MO_TRATO',      'Mano de Obra · Trato'),
        ('MAQUINARIA',    'Arriendo Maquinaria'),
        ('HERRAMIENTAS',  'Herramientas y Equipos'),
        ('COMBUSTIBLE',   'Combustible'),
        ('TRANSPORTE',    'Fletes y Transporte'),
        ('ALOJAMIENTO',   'Alojamiento / Arriendo'),
        ('ALIMENTACION',  'Alimentación'),
        ('VIATICOS',      'Viáticos y Movilización'),
        ('EPP',           'Implementos de Seguridad (EPP)'),
        ('OFICINA',       'Gastos de Oficina'),
        ('OTROS',         'Otros Gastos'),
    ]
    TIPO_DOC = [
        ('BOLETA','Boleta'),('FACTURA','Factura'),
        ('LIQUIDACION','Liquidación de Sueldo'),
        ('CONTRATO','Contrato'),('OTRO','Otro'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gastos')
    obra = models.ForeignKey(Obra, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    imagen = CloudinaryField('boleta', resource_type='auto', blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    tipo_documento = models.CharField(max_length=15, choices=TIPO_DOC, default='BOLETA')
    rut_emisor = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    nombre_emisor = models.CharField(max_length=150, blank=True, null=True)
    folio = models.CharField(max_length=50, blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True, db_index=True)
    monto_neto = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    iva = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    monto_total = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    tiene_iva = models.BooleanField(default=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='MATERIALES', db_index=True)
    descripcion = models.TextField(blank=True, null=True)
    nombre_trabajador = models.CharField(max_length=150, blank=True, null=True)
    rut_trabajador = models.CharField(max_length=20, blank=True, null=True)
    dias_trabajados = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    valor_dia = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    direccion_alojamiento = models.CharField(max_length=200, blank=True, null=True)
    num_personas = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    num_noches = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    valor_noche = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    procesado_exitosamente = models.BooleanField(default=False)
    nota_error = models.TextField(blank=True, null=True)
    validado_sii = models.BooleanField(default=False)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
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
        return f"Gasto #{self.id} - ${self.monto_total:,}"
    @property
    def estado(self):
        if not self.monto_total: return 'pendiente'
        if not self.rut_emisor: return 'incompleto'
        if self.validado_sii: return 'validado_sii'
        return 'completo'


class Presupuesto(models.Model):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='presupuestos_legacy')
    categoria = models.CharField(max_length=20, choices=Gasto.CATEGORIAS)
    monto = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    class Meta:
        unique_together = ('obra', 'categoria')
        verbose_name = "Presupuesto"
        verbose_name_plural = "Presupuestos"
    def __str__(self):
        return f"{self.obra.nombre} - {self.get_categoria_display()}: ${self.monto}"


# ── 1. CURVA S ────────────────────────────────────────────────────────────────
class PlanificacionMensual(models.Model):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='planificacion_mensual')
    anio = models.IntegerField(verbose_name="Año")
    mes = models.IntegerField(verbose_name="Mes", validators=[MinValueValidator(1), MaxValueValidator(12)])
    categoria = models.CharField(max_length=20, choices=Gasto.CATEGORIAS)
    monto_planificado = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    class Meta:
        unique_together = ('obra', 'anio', 'mes', 'categoria')
        ordering = ['anio', 'mes', 'categoria']
        verbose_name = "Planificación mensual"
        verbose_name_plural = "Planificaciones mensuales"
    def __str__(self):
        return f"{self.obra.nombre} · {self.mes}/{self.anio} · {self.categoria}"


# ── 2. SUBCONTRATOS ───────────────────────────────────────────────────────────
class Subcontrato(models.Model):
    ESTADOS = [
        ('ACTIVO','En ejecución'),('PAUSADO','Pausado'),
        ('TERMINADO','Terminado'),('DISPUTA','En disputa'),
    ]
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='subcontratos')
    nombre = models.CharField(max_length=150, verbose_name="Empresa / Persona")
    rut = models.CharField(max_length=20, blank=True, null=True)
    descripcion_trabajo = models.TextField(verbose_name="Descripción del trabajo")
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(blank=True, null=True)
    monto_contrato = models.IntegerField(validators=[MinValueValidator(0)])
    estado = models.CharField(max_length=20, choices=ESTADOS, default='ACTIVO')
    notas = models.TextField(blank=True, null=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Subcontrato"
        verbose_name_plural = "Subcontratos"
    def __str__(self):
        return f"{self.nombre} — {self.obra.nombre}"
    @property
    def monto_pagado(self):
        if not self.rut:
            return 0
        return Gasto.objects.filter(
            obra=self.obra, categoria='MO_SUBCONTRATA', rut_emisor=self.rut
        ).aggregate(total=models.Sum('monto_total'))['total'] or 0
    @property
    def monto_pendiente(self):
        return max(self.monto_contrato - self.monto_pagado, 0)
    @property
    def porcentaje_pagado(self):
        if self.monto_contrato == 0: return 0
        return round((self.monto_pagado / self.monto_contrato) * 100, 1)


# ── 3. AVANCE FÍSICO ──────────────────────────────────────────────────────────
class AvanceFisico(models.Model):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='avances_fisicos')
    fecha = models.DateField(verbose_name="Fecha del reporte")
    categoria = models.CharField(max_length=20, choices=Gasto.CATEGORIAS)
    porcentaje_avance = models.DecimalField(
        max_digits=5, decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    descripcion = models.TextField(blank=True, null=True)
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    class Meta:
        unique_together = ('obra', 'fecha', 'categoria')
        ordering = ['-fecha', 'categoria']
        verbose_name = "Avance físico"
        verbose_name_plural = "Avances físicos"
    def __str__(self):
        return f"{self.obra.nombre} · {self.fecha} · {self.categoria}: {self.porcentaje_avance}%"