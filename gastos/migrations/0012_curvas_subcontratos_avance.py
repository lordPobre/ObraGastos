from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('gastos', '0011_presupuesto_profundo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── 1. CURVA S — PlanificacionMensual ────────────────────────────────
        # Permite ingresar cuánto se planea gastar por mes y categoría
        migrations.CreateModel(
            name='PlanificacionMensual',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('anio', models.IntegerField(verbose_name='Año')),
                ('mes', models.IntegerField(
                    verbose_name='Mes (1-12)',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(12),
                    ]
                )),
                ('categoria', models.CharField(max_length=20, verbose_name='Categoría')),
                ('monto_planificado', models.IntegerField(
                    default=0,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='Monto planificado CLP'
                )),
                ('obra', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='planificacion_mensual',
                    to='gastos.obra',
                    verbose_name='Obra'
                )),
            ],
            options={
                'verbose_name': 'Planificación mensual',
                'verbose_name_plural': 'Planificaciones mensuales',
                'ordering': ['anio', 'mes', 'categoria'],
                'unique_together': {('obra', 'anio', 'mes', 'categoria')},
            },
        ),

        # ── 2. SUBCONTRATOS ────────────────────────────────────────────────
        migrations.CreateModel(
            name='Subcontrato',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=150, verbose_name='Nombre empresa / persona')),
                ('rut', models.CharField(max_length=20, blank=True, null=True, verbose_name='RUT')),
                ('descripcion_trabajo', models.TextField(verbose_name='Descripción del trabajo')),
                ('fecha_inicio', models.DateField(verbose_name='Fecha inicio')),
                ('fecha_termino', models.DateField(blank=True, null=True, verbose_name='Fecha término estimada')),
                ('monto_contrato', models.IntegerField(
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='Monto total del contrato (CLP)'
                )),
                ('estado', models.CharField(
                    max_length=20,
                    choices=[
                        ('ACTIVO', 'En ejecución'),
                        ('PAUSADO', 'Pausado'),
                        ('TERMINADO', 'Terminado'),
                        ('DISPUTA', 'En disputa'),
                    ],
                    default='ACTIVO',
                    verbose_name='Estado'
                )),
                ('notas', models.TextField(blank=True, null=True, verbose_name='Notas')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('obra', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subcontratos',
                    to='gastos.obra',
                    verbose_name='Obra'
                )),
                ('creado_por', models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Creado por'
                )),
            ],
            options={
                'verbose_name': 'Subcontrato',
                'verbose_name_plural': 'Subcontratos',
                'ordering': ['-created_at'],
            },
        ),

        # ── 3. AVANCE FÍSICO ──────────────────────────────────────────────
        migrations.CreateModel(
            name='AvanceFisico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('fecha', models.DateField(verbose_name='Fecha del reporte')),
                ('categoria', models.CharField(max_length=20, verbose_name='Partida / Categoría')),
                ('porcentaje_avance', models.DecimalField(
                    max_digits=5, decimal_places=1,
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(100),
                    ],
                    verbose_name='% avance físico'
                )),
                ('descripcion', models.TextField(blank=True, null=True, verbose_name='Observaciones')),
                ('obra', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='avances_fisicos',
                    to='gastos.obra',
                    verbose_name='Obra'
                )),
                ('registrado_por', models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Registrado por'
                )),
            ],
            options={
                'verbose_name': 'Avance físico',
                'verbose_name_plural': 'Avances físicos',
                'ordering': ['-fecha', 'categoria'],
                'unique_together': {('obra', 'fecha', 'categoria')},
            },
        ),
    ]
