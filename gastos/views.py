import io
import os
import logging
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Font, PatternFill
from PIL import Image

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.contrib import messages
from django.urls import reverse
from django.utils.http import urlencode
from django.http import HttpResponse, Http404, HttpResponseForbidden
from django.db.models.functions import TruncMonth
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from .models import Gasto, Empresa, Obra, Presupuesto
from .forms import GastoForm, CargaMasivaForm, ObraForm
from .utils import procesar_boleta_chilena
from .sharepoint import respaldar_en_sharepoint
import tempfile
import requests as req

logger = logging.getLogger(__name__)


# =====================================================
# HELPERS DE SEGURIDAD MULTI-TENANT
# =====================================================
def get_empresa_usuario(user):
    """Retorna la empresa del usuario o None si no tiene."""
    if hasattr(user, 'perfil') and user.perfil.empresa:
        return user.perfil.empresa
    return None


def get_gastos_empresa(user):
    """
    Retorna SOLO los gastos de la empresa del usuario.

    CRÍTICO: Esta función es la barrera de aislamiento multi-tenant.
    Nunca devuelve gastos de otras empresas.
    """
    if user.is_superuser:
        return Gasto.objects.all()

    empresa = get_empresa_usuario(user)
    if empresa:
        return Gasto.objects.filter(empresa=empresa)

    return Gasto.objects.none()


def get_gasto_seguro_o_404(user, pk):
    """
    Obtiene un gasto verificando que pertenezca a la empresa del usuario.

    Esta función reemplaza al inseguro get_object_or_404(Gasto, pk=pk).
    """
    gasto = get_object_or_404(Gasto, pk=pk)

    if user.is_superuser:
        return gasto

    empresa = get_empresa_usuario(user)
    if not empresa or gasto.empresa != empresa:
        raise Http404("Gasto no encontrado.")

    return gasto


def get_obra_segura_o_404(user, pk):
    """Obtiene una obra verificando que pertenezca a la empresa del usuario."""
    obra = get_object_or_404(Obra, pk=pk)

    if user.is_superuser:
        return obra

    empresa = get_empresa_usuario(user)
    if not empresa or obra.empresa != empresa:
        raise Http404("Obra no encontrada.")

    return obra


# =====================================================
# DASHBOARD
# =====================================================
@login_required
def dashboard(request):
    gastos = get_gastos_empresa(request.user)
    empresa = get_empresa_usuario(request.user)

    obras = Obra.objects.none()
    obra_seleccionada = request.GET.get('obra') or request.session.get('obra_seleccionada', '')

    if empresa:
        obras = Obra.objects.filter(empresa=empresa, activo=True)
        if obra_seleccionada:
            try:
                # Verificar que la obra pertenezca a la empresa
                obras.get(pk=obra_seleccionada)
                gastos = gastos.filter(obra_id=obra_seleccionada)
                request.session['obra_seleccionada'] = obra_seleccionada
            except Obra.DoesNotExist:
                obra_seleccionada = ''
                request.session.pop('obra_seleccionada', None)
        elif obra_seleccionada == '':
            request.session.pop('obra_seleccionada', None)

    hoy = date.today()
    total_validado = gastos.aggregate(Sum('monto_total'))['monto_total__sum'] or 0
    cantidad_gastos = gastos.count()

    # PRESUPUESTOS
    presupuesto_total = 0
    if obra_seleccionada:
        presupuesto_total = Presupuesto.objects.filter(
            obra_id=obra_seleccionada
        ).aggregate(Sum('monto'))['monto__sum'] or 0
    elif obras.exists():
        presupuesto_total = Presupuesto.objects.filter(
            obra__in=obras
        ).aggregate(Sum('monto'))['monto__sum'] or 0

    presupuesto_disponible = presupuesto_total - total_validado
    porcentaje_gastado = 0
    if presupuesto_total > 0:
        porcentaje_gastado = round((total_validado / presupuesto_total) * 100, 1)

    # EVOLUCIÓN MENSUAL
    gastos_por_mes = (
        gastos
        .annotate(mes=TruncMonth('fecha_emision'))
        .values('mes')
        .annotate(total=Sum('monto_total'))
        .order_by('mes')
    )

    labels_grafico = []
    data_grafico = []
    for g in gastos_por_mes:
        if g['mes']:
            labels_grafico.append(g['mes'].strftime("%Y-%m"))
            data_grafico.append(g['total'])

    # CATEGORÍAS
    resumen_categorias = (
        gastos.values('categoria').annotate(total=Sum('monto_total')).order_by('categoria')
    )
    gastos_dict = {item['categoria']: item['total'] for item in resumen_categorias}

    presupuesto_dict = {}
    if obra_seleccionada:
        presupuesto_dict = {
            p.categoria: p.monto
            for p in Presupuesto.objects.filter(obra_id=obra_seleccionada)
        }

    labels_cat = []
    data_cat = []
    data_presup = []
    for codigo, nombre in Gasto.CATEGORIAS:
        real = gastos_dict.get(codigo, 0)
        meta = presupuesto_dict.get(codigo, 0)
        if real > 0 or meta > 0:
            labels_cat.append(nombre)
            data_cat.append(real)
            data_presup.append(meta)

    ultimos_gastos = gastos.order_by('-fecha_emision', '-id')[:5]

    context = {
        'cantidad_gastos': cantidad_gastos,
        'total_validado': total_validado,
        'presupuesto_total': presupuesto_total,
        'presupuesto_disponible': presupuesto_disponible,
        'porcentaje_gastado': porcentaje_gastado,
        'labels_grafico': labels_grafico,
        'data_grafico': data_grafico,
        'ultimos_gastos': ultimos_gastos,
        'labels_cat': labels_cat,
        'data_cat': data_cat,
        'data_presup': data_presup,
        'fecha_actual': hoy,
        'obras': obras,
        'obra_seleccionada': obra_seleccionada,
    }

    return render(request, 'gastos/dashboard.html', context)


# =====================================================
# CRUD DE GASTOS
# =====================================================
@login_required
def crear_gasto(request):
    if request.method == 'POST':
        form = GastoForm(request.user, request.POST, request.FILES)

        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.usuario = request.user

            empresa = get_empresa_usuario(request.user)
            if empresa:
                gasto.empresa = empresa

            gasto.save()

            # OCR
            # OCR
            ocr_exitoso = False
            if gasto.imagen:
                try:
                    try:
                        ruta = gasto.imagen.path
                    except (NotImplementedError, AttributeError):
                        # Cloudinary o S3 — descargamos temporalmente
                        import tempfile
                        import requests as req
                        url = gasto.imagen.url
                        resp = req.get(url, timeout=30)
                        sufijo = '.' + gasto.imagen.name.split('.')[-1] if '.' in str(gasto.imagen.name) else '.pdf'
                        with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
                            tmp.write(resp.content)
                            ruta = tmp.name

                    resultado = procesar_boleta_chilena(ruta)

                    if 'error' not in resultado:
                        if resultado.get('monto_total'):
                            gasto.monto_total = int(resultado['monto_total'])
                        if resultado.get('rut_emisor'):
                            gasto.rut_emisor = resultado['rut_emisor']
                        if resultado.get('folio'):
                            gasto.folio = str(resultado['folio'])

                        fecha_str = resultado.get('fecha_emision')
                        if fecha_str:
                            try:
                                gasto.fecha_emision = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass

                        gasto.procesado_exitosamente = True
                        gasto.save()
                        ocr_exitoso = True
                        messages.success(request, "¡Boleta leída! Por favor confirma los datos.")
                    else:
                        gasto.nota_error = resultado.get('error', 'Error desconocido')
                        gasto.save()
                        messages.warning(request, f"Escáner: {resultado['error']}")
                except Exception as e:
                    logger.exception(f"Error procesando imagen del gasto #{gasto.id}")
                    messages.warning(request, f"Error procesando imagen: {e}")

            # Backup en SharePoint solo si todo OK
            if ocr_exitoso:
                try:
                    respaldar_en_sharepoint(gasto)
                except Exception as e:
                    logger.warning(f"SharePoint falló para gasto #{gasto.id}: {e}")

            return redirect('editar_gasto', pk=gasto.pk)
    else:
        form = GastoForm(request.user)

    return render(request, 'gastos/crear_gasto.html', {'form': form, 'titulo': 'Nuevo Gasto'})


@login_required
def editar_gasto(request, pk):
    # SEGURIDAD: validar pertenencia
    gasto = get_gasto_seguro_o_404(request.user, pk)

    if request.method == 'POST':
        form = GastoForm(request.user, request.POST, request.FILES, instance=gasto)

        if form.is_valid():
            gasto = form.save()

            if 'imagen' in form.changed_data or 'obra' in form.changed_data:
                logger.info(f"[EDICIÓN] Resincronizando gasto #{gasto.id}")
                try:
                    respaldar_en_sharepoint(gasto)
                except Exception as e:
                    logger.warning(f"SharePoint falló al resincronizar gasto #{gasto.id}: {e}")

            messages.success(request, "¡Gasto actualizado correctamente!")
            return redirect('historial_gastos')
    else:
        form = GastoForm(request.user, instance=gasto)

    return render(request, 'gastos/editar_gasto.html', {
        'form': form,
        'titulo': f'Editar Gasto #{gasto.folio or gasto.id}',
        'gasto': gasto
    })


@login_required
def eliminar_gasto(request, pk):
    # SEGURIDAD: validar pertenencia
    gasto = get_gasto_seguro_o_404(request.user, pk)

    if request.method == 'POST':
        gasto.delete()
        messages.success(request, "Gasto eliminado.")
        return redirect('historial_gastos')

    return render(request, 'gastos/eliminar_gasto.html', {'object': gasto})


# =====================================================
# HISTORIAL
# =====================================================
@login_required
def historial_gastos(request):
    empresa = get_empresa_usuario(request.user)

    if empresa:
        gastos = Gasto.objects.filter(empresa=empresa)
        obras = Obra.objects.filter(empresa=empresa, activo=True)
        categorias_brutas = (
            gastos
            .exclude(categoria__isnull=True)
            .exclude(categoria__exact='')
            .values_list('categoria', flat=True)
            .distinct()
        )
        categorias_disponibles = []
        for cat in categorias_brutas:
            nombre_bonito = cat.replace('_', ' ').title().replace(' De ', ' de ')
            categorias_disponibles.append({
                'valor_db': cat,
                'nombre_visible': nombre_bonito
            })
    else:
        gastos = Gasto.objects.none()
        obras = Obra.objects.none()
        categorias_disponibles = []

    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    obra_id = request.GET.get('obra_id')
    categoria_seleccionada = request.GET.get('categoria')
    busqueda = request.GET.get('q', '').strip()

    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)
    if obra_id:
        gastos = gastos.filter(obra_id=obra_id)
    if categoria_seleccionada:
        gastos = gastos.filter(categoria=categoria_seleccionada)
    if busqueda:
        # NUEVA: búsqueda global por RUT, folio o descripción
        gastos = gastos.filter(
            Q(rut_emisor__icontains=busqueda) |
            Q(folio__icontains=busqueda) |
            Q(descripcion__icontains=busqueda)
        )

    gastos = gastos.order_by('-fecha_emision', '-id')
    total_filtrado = gastos.aggregate(total=Sum('monto_total'))['total'] or 0

    context = {
        'gastos': gastos,
        'obras': obras,
        'categorias_disponibles': categorias_disponibles,
        'total_filtrado': total_filtrado,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'obra_seleccionada': obra_id,
        'categoria_seleccionada': categoria_seleccionada,
        'busqueda': busqueda,
    }
    return render(request, 'gastos/historial.html', context)


# =====================================================
# CARGA MASIVA (BUG CRÍTICO CORREGIDO)
# =====================================================
@login_required
def carga_masiva(request):
    if request.method == 'POST':
        logger.info("Iniciando carga masiva...")

        form = CargaMasivaForm(request.POST, request.FILES)

        if form.is_valid():
            archivos = request.FILES.getlist('imagenes')
            obra_id = request.POST.get('obra_id') or None
            empresa = get_empresa_usuario(request.user)

            # Validar la obra si se mandó
            obra = None
            if obra_id and empresa:
                try:
                    obra = Obra.objects.get(pk=obra_id, empresa=empresa)
                except Obra.DoesNotExist:
                    obra = None

            logger.info(f"Recibidos {len(archivos)} archivos.")

            procesados = 0
            fallidos = 0

            for f in archivos:
                try:
                    # CORRECCIÓN CRÍTICA: ahora SÍ asignamos empresa y obra
                    nuevo_gasto = Gasto(
                        usuario=request.user,
                        empresa=empresa,
                        obra=obra,
                        imagen=f,
                        procesado_exitosamente=False
                    )
                    nuevo_gasto.save()

                    resultado = procesar_boleta_chilena(nuevo_gasto.imagen.path)

                    if 'error' not in resultado:
                        if resultado.get('monto_total'):
                            nuevo_gasto.monto_total = int(resultado['monto_total'])
                        if resultado.get('rut_emisor'):
                            nuevo_gasto.rut_emisor = resultado['rut_emisor']
                        if resultado.get('folio'):
                            nuevo_gasto.folio = str(resultado['folio'])

                        fecha_str = resultado.get('fecha_emision')
                        if fecha_str:
                            try:
                                nuevo_gasto.fecha_emision = datetime.strptime(
                                    fecha_str, '%Y-%m-%d'
                                ).date()
                            except ValueError:
                                pass

                        nuevo_gasto.procesado_exitosamente = True
                        nuevo_gasto.save()
                        procesados += 1

                        # Backup async
                        try:
                            respaldar_en_sharepoint(nuevo_gasto)
                        except Exception as e:
                            logger.warning(f"SharePoint falló: {e}")
                    else:
                        nuevo_gasto.nota_error = resultado.get('error', '')
                        nuevo_gasto.save()
                        fallidos += 1

                except Exception as e:
                    logger.exception(f"Error crítico en carga masiva con {f.name}: {e}")
                    fallidos += 1

            if procesados > 0:
                messages.success(request, f"¡Éxito! {procesados} boletas procesadas correctamente.")
            if fallidos > 0:
                messages.warning(request, f"{fallidos} boletas no se pudieron leer. Revísalas en el historial.")

            return redirect('historial_gastos')

        else:
            logger.warning(f"Formulario inválido: {form.errors}")
            messages.error(request, "Error en el formulario.")
    else:
        form = CargaMasivaForm()

    # Pasar las obras al template
    empresa = get_empresa_usuario(request.user)
    obras = Obra.objects.filter(empresa=empresa, activo=True) if empresa else []

    return render(request, 'gastos/carga_masiva.html', {'form': form, 'obras': obras})


@login_required
def eliminar_masivo(request):
    if request.method != 'POST':
        return redirect('historial_gastos')

    ids_a_borrar = request.POST.getlist('gastos_ids')

    if ids_a_borrar:
        empresa = get_empresa_usuario(request.user)

        # SEGURIDAD: solo borrar gastos de la misma empresa
        if request.user.is_superuser:
            qs = Gasto.objects.filter(id__in=ids_a_borrar)
        elif empresa:
            qs = Gasto.objects.filter(id__in=ids_a_borrar, empresa=empresa)
        else:
            qs = Gasto.objects.none()

        cantidad, _ = qs.delete()

        if cantidad > 0:
            messages.success(request, f"Se eliminaron {cantidad} boletas.")
        else:
            messages.warning(request, "No se pudo eliminar.")

    # Mantener filtros al volver
    f_inicio = request.POST.get('fecha_inicio_filtro')
    f_fin = request.POST.get('fecha_fin_filtro')
    base_url = reverse('historial_gastos')

    parametros = {}
    if f_inicio:
        parametros['fecha_inicio'] = f_inicio
    if f_fin:
        parametros['fecha_fin'] = f_fin

    if parametros:
        return redirect(f"{base_url}?{urlencode(parametros)}")

    return redirect('historial_gastos')


# =====================================================
# EXPORTAR (CON AISLAMIENTO MULTI-TENANT)
# =====================================================
@login_required
def exportar_excel(request):
    # CORRECCIÓN CRÍTICA: filtramos por empresa
    gastos = get_gastos_empresa(request.user)

    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)

    gastos = gastos.order_by('-fecha_emision')

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename=Reporte_Gastos_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gastos"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")

    headers = ["Fecha", "RUT Emisor", "Folio", "Categoría", "Obra", "Monto Total", "Usuario"]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    total = 0
    for gasto in gastos:
        ws.append([
            gasto.fecha_emision,
            gasto.rut_emisor or '',
            gasto.folio or '',
            gasto.get_categoria_display(),
            gasto.obra.nombre if gasto.obra else '',
            gasto.monto_total,
            gasto.usuario.username if gasto.usuario else '',
        ])
        total += gasto.monto_total

    ws.append(["", "", "", "", "TOTAL ACUMULADO:", total, ""])
    ws.cell(row=ws.max_row, column=6).font = Font(bold=True)

    # Ajustar ancho de columnas
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)

    wb.save(response)
    return response


@login_required
def exportar_pdf(request):
    # CORRECCIÓN CRÍTICA: filtramos por empresa
    gastos = get_gastos_empresa(request.user)

    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)

    gastos = gastos.order_by('-fecha_emision')
    total = gastos.aggregate(Sum('monto_total'))['monto_total__sum'] or 0

    empresa = get_empresa_usuario(request.user)

    context = {
        'gastos': gastos,
        'total': total,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'empresa': empresa.nombre if empresa else 'Sin Empresa',
    }

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_gastos.pdf"'

    html = render_to_string('gastos/reporte_pdf.html', context)
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Error generando el PDF', status=500)
    return response


# =====================================================
# OBRAS Y PRESUPUESTOS
# =====================================================
@login_required
def lista_obras(request):
    empresa = get_empresa_usuario(request.user)
    obras = Obra.objects.filter(empresa=empresa) if empresa else Obra.objects.none()
    return render(request, 'gastos/lista_obras.html', {'obras': obras})


@login_required
def crear_obra(request):
    if request.method == 'POST':
        form = ObraForm(request.POST)
        if form.is_valid():
            obra = form.save(commit=False)
            empresa = get_empresa_usuario(request.user)
            if empresa:
                obra.empresa = empresa
                obra.save()
                messages.success(request, "¡Proyecto creado correctamente!")
                return redirect('lista_obras')
            else:
                messages.error(request, "No tienes empresa asignada.")
    else:
        form = ObraForm()

    return render(request, 'gastos/crear_obra.html', {'form': form})


@login_required
def definir_presupuesto(request, obra_id):
    # SEGURIDAD: validar pertenencia
    obra = get_obra_segura_o_404(request.user, obra_id)

    categorias = Gasto.CATEGORIAS

    if request.method == 'POST':
        for codigo, nombre in categorias:
            monto_str = request.POST.get(f'presupuesto_{codigo}')
            if monto_str:
                try:
                    monto = int(monto_str)
                    if monto < 0:
                        continue
                    Presupuesto.objects.update_or_create(
                        obra=obra,
                        categoria=codigo,
                        defaults={'monto': monto}
                    )
                except (ValueError, TypeError):
                    pass

        messages.success(request, "¡Presupuesto actualizado correctamente!")
        return redirect('lista_obras')

    presupuestos_actuales = {
        p.categoria: p.monto
        for p in Presupuesto.objects.filter(obra=obra)
    }

    datos_tabla = [
        {
            'codigo': codigo,
            'nombre': nombre,
            'monto_actual': presupuestos_actuales.get(codigo, 0)
        }
        for codigo, nombre in categorias
    ]

    return render(request, 'gastos/definir_presupuesto.html', {
        'obra': obra,
        'datos_tabla': datos_tabla
    })


# =====================================================
# DESCARGA DE BOLETA (CON AISLAMIENTO)
# =====================================================
@login_required
def descargar_boleta_pdf(request, pk):
    # SEGURIDAD: validar pertenencia
    gasto = get_gasto_seguro_o_404(request.user, pk)

    if not gasto.imagen or not hasattr(gasto.imagen, 'path'):
        raise Http404("Este gasto no tiene archivo adjunto.")

    ruta_archivo = gasto.imagen.path
    if not os.path.exists(ruta_archivo):
        raise Http404("El archivo físico no existe.")

    extension = os.path.splitext(ruta_archivo)[1].lower()
    nombre_descarga = f"Boleta_{gasto.folio or 'SF'}_{gasto.rut_emisor or 'SinRut'}.pdf"

    if extension == '.pdf':
        with open(ruta_archivo, 'rb') as pdf:
            response = HttpResponse(pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_descarga}"'
            return response

    elif extension in ('.jpg', '.jpeg', '.png'):
        try:
            imagen = Image.open(ruta_archivo)
            if imagen.mode in ("RGBA", "P"):
                imagen = imagen.convert("RGB")

            buffer = io.BytesIO()
            imagen.save(buffer, format='PDF', resolution=100.0)
            buffer.seek(0)

            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{nombre_descarga}"'
            return response

        except Exception as e:
            logger.error(f"Error convirtiendo imagen a PDF: {e}")
            return HttpResponse(f"Error: {e}", status=500)

    return HttpResponse("Formato no soportado.", status=400)
