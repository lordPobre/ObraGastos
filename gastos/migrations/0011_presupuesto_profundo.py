from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
    ('gastos', '0010_alter_gasto_imagen'),
    ]

    operations = [
        # ── Nuevos campos en Gasto ────────────────────────────────────────────

        # Tipo de documento
        migrations.AddField(
            model_name='gasto',
            name='tipo_documento',
            field=models.CharField(
                choices=[('BOLETA', 'Boleta'), ('FACTURA', 'Factura'),
                         ('LIQUIDACION', 'Liquidación de Sueldo'),
                         ('CONTRATO', 'Contrato'), ('OTRO', 'Otro')],
                default='BOLETA', max_length=15, verbose_name='Tipo de documento'
            ),
        ),

        # Nombre del emisor
        migrations.AddField(
            model_name='gasto',
            name='nombre_emisor',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Proveedor / Emisor'),
        ),

        # Montos desglosados
        migrations.AddField(
            model_name='gasto',
            name='monto_neto',
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Monto neto (sin IVA)'
            ),
        ),
        migrations.AddField(
            model_name='gasto',
            name='iva',
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='IVA (19%)'
            ),
        ),
        migrations.AddField(
            model_name='gasto',
            name='tiene_iva',
            field=models.BooleanField(default=True, verbose_name='¿Afecto a IVA?'),
        ),

        # Nuevas categorías (ampliar max_length de categoria)
        migrations.AlterField(
            model_name='gasto',
            name='categoria',
            field=models.CharField(
                choices=[
                    ('MATERIALES', 'Materiales de Construcción'),
                    ('MO_CONTRATA', 'Mano de Obra · Contrata'),
                    ('MO_SUBCONTRATA', 'Mano de Obra · Subcontrata'),
                    ('MO_JORNAL', 'Mano de Obra · Jornal / Día'),
                    ('MO_TRATO', 'Mano de Obra · Trato'),
                    ('MAQUINARIA', 'Arriendo Maquinaria'),
                    ('HERRAMIENTAS', 'Herramientas y Equipos'),
                    ('COMBUSTIBLE', 'Combustible'),
                    ('TRANSPORTE', 'Fletes y Transporte'),
                    ('ALOJAMIENTO', 'Alojamiento / Arriendo'),
                    ('ALIMENTACION', 'Alimentación'),
                    ('VIATICOS', 'Viáticos y Movilización'),
                    ('EPP', 'Implementos de Seguridad (EPP)'),
                    ('OFICINA', 'Gastos de Oficina'),
                    ('OTROS', 'Otros Gastos'),
                ],
                db_index=True, default='MATERIALES',
                max_length=20, verbose_name='Categoría del Gasto'
            ),
        ),

        # Campos mano de obra
        migrations.AddField(
            model_name='gasto',
            name='nombre_trabajador',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Nombre trabajador / empresa'),
        ),
        migrations.AddField(
            model_name='gasto',
            name='rut_trabajador',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='RUT trabajador / empresa'),
        ),
        migrations.AddField(
            model_name='gasto',
            name='dias_trabajados',
            field=models.IntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name='Días trabajados'
            ),
        ),
        migrations.AddField(
            model_name='gasto',
            name='valor_dia',
            field=models.IntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Valor por día (CLP)'
            ),
        ),

        # Campos alojamiento
        migrations.AddField(
            model_name='gasto',
            name='direccion_alojamiento',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Dirección del alojamiento'),
        ),
        migrations.AddField(
            model_name='gasto',
            name='num_personas',
            field=models.IntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name='N° de personas'
            ),
        ),
        migrations.AddField(
            model_name='gasto',
            name='num_noches',
            field=models.IntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name='N° de noches'
            ),
        ),
        migrations.AddField(
            model_name='gasto',
            name='valor_noche',
            field=models.IntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Valor por noche (CLP)'
            ),
        ),

        # ── Nuevo modelo ItemPresupuesto ──────────────────────────────────────
        migrations.CreateModel(
            name='ItemPresupuesto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('categoria', models.CharField(
                    choices=[
                        ('MATERIALES', 'Materiales de Construcción'),
                        ('MO_CONTRATA', 'Mano de Obra · Contrata'),
                        ('MO_SUBCONTRATA', 'Mano de Obra · Subcontrata'),
                        ('MO_JORNAL', 'Mano de Obra · Jornal / Día'),
                        ('MO_TRATO', 'Mano de Obra · Trato'),
                        ('MAQUINARIA', 'Arriendo Maquinaria'),
                        ('HERRAMIENTAS', 'Herramientas y Equipos'),
                        ('COMBUSTIBLE', 'Combustible'),
                        ('TRANSPORTE', 'Fletes y Transporte'),
                        ('ALOJAMIENTO', 'Alojamiento / Arriendo'),
                        ('ALIMENTACION', 'Alimentación'),
                        ('VIATICOS', 'Viáticos y Movilización'),
                        ('EPP', 'Implementos de Seguridad (EPP)'),
                        ('OFICINA', 'Gastos de Oficina'),
                        ('OTROS', 'Otros Gastos'),
                    ],
                    max_length=20
                )),
                ('monto_neto_presupuestado', models.IntegerField(
                    default=0,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='Monto neto presupuestado'
                )),
                ('considera_iva', models.BooleanField(default=True, verbose_name='¿Considera IVA en el presupuesto?')),
                ('notas', models.TextField(blank=True, null=True, verbose_name='Notas / Aclaraciones')),
                ('obra', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='presupuestos',
                    to='gastos.obra'
                )),
            ],
            options={
                'verbose_name': 'Ítem de Presupuesto',
                'verbose_name_plural': 'Ítems de Presupuesto',
                'ordering': ['categoria'],
                'unique_together': {('obra', 'categoria')},
            },
        ),

        # Renombrar related_name de Presupuesto legacy para evitar conflicto
        migrations.AlterField(
            model_name='presupuesto',
            name='obra',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='presupuestos_legacy',
                to='gastos.obra'
            ),
        ),
    ]
