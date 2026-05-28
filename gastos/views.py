import io
import os
import logging
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Font, PatternFill
from PIL import Image

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Avg
from django.db import models as django_models
from django.contrib import messages
from django.urls import reverse
from django.utils.http import urlencode
from django.http import HttpResponse, Http404
from django.db.models.functions import TruncMonth, TruncDay, TruncYear
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from .models import Gasto, Empresa, Obra, Presupuesto
from .forms import GastoForm, CargaMasivaForm, ObraForm
from .utils import procesar_boleta_chilena
from .sharepoint import respaldar_en_sharepoint
import tempfile
import requests as req
import fitz

logger = logging.getLogger(__name__)


# =====================================================
# HELPERS DE SEGURIDAD MULTI-TENANT
# =====================================================
def get_empresa_usuario(user):
    if hasattr(user, 'perfil') and user.perfil.empresa:
        return user.perfil.empresa
    return None


def get_gastos_empresa(user):
    if user.is_superuser:
        return Gasto.objects.all()
    empresa = get_empresa_usuario(user)
    if empresa:
        return Gasto.objects.filter(empresa=empresa)
    return Gasto.objects.none()


def get_gasto_seguro_o_404(user, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    if user.is_superuser:
        return gasto
    empresa = get_empresa_usuario(user)
    if not empresa or gasto.empresa != empresa:
        raise Http404("Gasto no encontrado.")
    return gasto


def get_obra_segura_o_404(user, pk):
    obra = get_object_or_404(Obra, pk=pk)
    if user.is_superuser:
        return obra
    empresa = get_empresa_usuario(user)
    if not empresa or obra.empresa != empresa:
        raise Http404("Obra no encontrada.")
    return obra


def pdf_a_imagen(archivo_file):
    import io
    from django.core.files.uploadedfile import InMemoryUploadedFile
    try:
        contenido = archivo_file.read()
        archivo_file.seek(0)
        doc = fitz.open(stream=contenido, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        img_io = io.BytesIO(img_bytes)
        nombre_png = archivo_file.name.replace('.pdf', '.png').replace('.PDF', '.png')
        return InMemoryUploadedFile(
            img_io, 'imagen', nombre_png,
            'image/png', len(img_bytes), None
        )
    except Exception as e:
        logger.warning(f"No se pudo convertir PDF a imagen: {e}")
        return None


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

    # EVOLUCIÓN — 3 granularidades
    def build_serie(trunc_fn, fmt):
        qs = (
            gastos
            .exclude(fecha_emision__isnull=True)
            .annotate(periodo=trunc_fn('fecha_emision'))
            .values('periodo')
            .annotate(total=Sum('monto_total'))
            .order_by('periodo')
        )
        labels, data = [], []
        for g in qs:
            if g['periodo']:
                labels.append(g['periodo'].strftime(fmt))
                data.append(g['total'])
        return labels, data

    labels_diario,  data_diario  = build_serie(TruncDay,   "%d/%m/%Y")
    labels_mensual, data_mensual = build_serie(TruncMonth,  "%m/%Y")
    labels_anual,   data_anual   = build_serie(TruncYear,   "%Y")

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
    alertas_presupuesto = []

    for codigo, nombre in Gasto.CATEGORIAS:
        real = gastos_dict.get(codigo, 0)
        meta = presupuesto_dict.get(codigo, 0)
        if real > 0 or meta > 0:
            labels_cat.append(nombre)
            data_cat.append(real)
            data_presup.append(meta)

        if meta > 0 and real > 0:
            pct = round((real / meta) * 100, 1)
            if pct >= 100:
                alertas_presupuesto.append({
                    'categoria': nombre, 'pct': pct,
                    'real': real, 'meta': meta, 'tipo': 'excedido',
                })
            elif pct >= 75:
                alertas_presupuesto.append({
                    'categoria': nombre, 'pct': pct,
                    'real': real, 'meta': meta, 'tipo': 'advertencia',
                })

    alertas_presupuesto.sort(key=lambda a: (0 if a['tipo'] == 'excedido' else 1, -a['pct']))

    ultimos_gastos = gastos.order_by('-fecha_emision', '-id')[:5]

    context = {
        'cantidad_gastos':      cantidad_gastos,
        'total_validado':       total_validado,
        'presupuesto_total':    presupuesto_total,
        'presupuesto_disponible': presupuesto_disponible,
        'porcentaje_gastado':   porcentaje_gastado,
        # Evolución — 3 granularidades
        'labels_diario':  labels_diario,
        'data_diario':    data_diario,
        'labels_mensual': labels_mensual,
        'data_mensual':   data_mensual,
        'labels_anual':   labels_anual,
        'data_anual':     data_anual,
        # Categorías y presupuesto
        'labels_cat':  labels_cat,
        'data_cat':    data_cat,
        'data_presup': data_presup,
        'alertas_presupuesto': alertas_presupuesto,
        # Misc
        'ultimos_gastos':   ultimos_gastos,
        'fecha_actual':     hoy,
        'obras':            obras,
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

            ocr_exitoso = False
            archivo = request.FILES.get('imagen')
            if archivo:
                try:
                    sufijo = '.' + archivo.name.split('.')[-1] if '.' in archivo.name else '.pdf'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
                        for chunk in archivo.chunks():
                            tmp.write(chunk)
                        ruta_tmp = tmp.name

                    archivo.seek(0)
                    resultado = procesar_boleta_chilena(ruta_tmp)

                    try:
                        os.remove(ruta_tmp)
                    except Exception:
                        pass

                    if 'error' not in resultado:
                        if resultado.get('monto_total'):
                            gasto.monto_total = int(resultado['monto_total'])
                        if resultado.get('monto_neto'):
                            gasto.monto_neto = int(resultado['monto_neto'])
                        if resultado.get('iva'):
                            gasto.iva = int(resultado['iva'])
                        elif gasto.monto_neto and gasto.monto_total:
                            gasto.iva = gasto.monto_total - gasto.monto_neto
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
                        ocr_exitoso = True
                        messages.success(request, "¡Boleta leída! Por favor confirma los datos.")
                    else:
                        gasto.nota_error = resultado.get('error', 'Error desconocido')
                        messages.warning(request, f"Escáner: {resultado['error']}")

                except Exception as e:
                    logger.exception("Error procesando OCR")
                    messages.warning(request, f"Error procesando imagen: {e}")

            # Convertir PDF a imagen para Cloudinary
            if archivo and archivo.name.lower().endswith('.pdf'):
                imagen_convertida = pdf_a_imagen(archivo)
                if imagen_convertida:
                    request.FILES['imagen'] = imagen_convertida
                    form.files['imagen'] = imagen_convertida
                    gasto.imagen = imagen_convertida

            gasto.save()

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
    gasto = get_gasto_seguro_o_404(request.user, pk)

    if request.method == 'POST':
        form = GastoForm(request.user, request.POST, request.FILES, instance=gasto)
        if form.is_valid():
            gasto = form.save()
            if 'imagen' in form.changed_data or 'obra' in form.changed_data:
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

    fecha_inicio          = request.GET.get('fecha_inicio')
    fecha_fin             = request.GET.get('fecha_fin')
    obra_id               = request.GET.get('obra_id')
    categoria_seleccionada = request.GET.get('categoria')
    busqueda              = request.GET.get('q', '').strip()

    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)
    if obra_id:
        gastos = gastos.filter(obra_id=obra_id)
    if categoria_seleccionada:
        gastos = gastos.filter(categoria=categoria_seleccionada)
    if busqueda:
        gastos = gastos.filter(
            Q(rut_emisor__icontains=busqueda) |
            Q(folio__icontains=busqueda) |
            Q(descripcion__icontains=busqueda)
        )

    gastos         = gastos.order_by('-fecha_emision', '-id')
    total_filtrado = gastos.aggregate(total=Sum('monto_total'))['total'] or 0
    total_neto     = gastos.aggregate(total=Sum('monto_neto'))['total']  or 0
    total_iva      = gastos.aggregate(total=Sum('iva'))['total']         or 0

    context = {
        'gastos': gastos,
        'obras': obras,
        'categorias_disponibles': categorias_disponibles,
        'total_filtrado': total_filtrado,
        'total_neto':     total_neto,
        'total_iva':      total_iva,
        'fecha_inicio':   fecha_inicio,
        'fecha_fin':      fecha_fin,
        'obra_seleccionada': obra_id,
        'categoria_seleccionada': categoria_seleccionada,
        'busqueda':       busqueda,
    }
    return render(request, 'gastos/historial.html', context)


# =====================================================
# CARGA MASIVA
# =====================================================
@login_required
def carga_masiva(request):
    if request.method == 'POST':
        form = CargaMasivaForm(request.POST, request.FILES)
        if form.is_valid():
            archivos  = request.FILES.getlist('imagenes')
            obra_id   = request.POST.get('obra_id') or None
            empresa   = get_empresa_usuario(request.user)

            obra = None
            if obra_id and empresa:
                try:
                    obra = Obra.objects.get(pk=obra_id, empresa=empresa)
                except Obra.DoesNotExist:
                    obra = None

            procesados = fallidos = 0

            for f in archivos:
                try:
                    sufijo = '.' + f.name.split('.')[-1] if '.' in f.name else '.pdf'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
                        for chunk in f.chunks():
                            tmp.write(chunk)
                        ruta_tmp = tmp.name

                    f.seek(0)

                    # Convertir PDF a imagen
                    archivo_guardar = f
                    if f.name.lower().endswith('.pdf'):
                        img_conv = pdf_a_imagen(f)
                        if img_conv:
                            archivo_guardar = img_conv

                    nuevo_gasto = Gasto(
                        usuario=request.user,
                        empresa=empresa,
                        obra=obra,
                        imagen=archivo_guardar,
                        procesado_exitosamente=False
                    )
                    nuevo_gasto.save()

                    resultado = procesar_boleta_chilena(ruta_tmp)
                    try:
                        os.remove(ruta_tmp)
                    except Exception:
                        pass

                    if 'error' not in resultado:
                        if resultado.get('monto_total'):
                            nuevo_gasto.monto_total = int(resultado['monto_total'])
                        if resultado.get('monto_neto'):
                            nuevo_gasto.monto_neto = int(resultado['monto_neto'])
                        if resultado.get('iva'):
                            nuevo_gasto.iva = int(resultado['iva'])
                        if resultado.get('rut_emisor'):
                            nuevo_gasto.rut_emisor = resultado['rut_emisor']
                        if resultado.get('folio'):
                            nuevo_gasto.folio = str(resultado['folio'])

                        fecha_str = resultado.get('fecha_emision')
                        if fecha_str:
                            try:
                                nuevo_gasto.fecha_emision = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass

                        nuevo_gasto.procesado_exitosamente = True
                        nuevo_gasto.save()
                        procesados += 1

                        try:
                            respaldar_en_sharepoint(nuevo_gasto)
                        except Exception as e:
                            logger.warning(f"SharePoint falló: {e}")
                    else:
                        nuevo_gasto.nota_error = resultado.get('error', '')
                        nuevo_gasto.save()
                        fallidos += 1

                except Exception as e:
                    logger.exception(f"Error en carga masiva con {f.name}: {e}")
                    fallidos += 1

            if procesados > 0:
                messages.success(request, f"¡Éxito! {procesados} boletas procesadas correctamente.")
            if fallidos > 0:
                messages.warning(request, f"{fallidos} boletas no se pudieron leer.")

            return redirect('historial_gastos')
        else:
            messages.error(request, "Error en el formulario.")
    else:
        form = CargaMasivaForm()

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

    f_inicio = request.POST.get('fecha_inicio_filtro')
    f_fin    = request.POST.get('fecha_fin_filtro')
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
# EXPORTAR
# =====================================================
@login_required
def exportar_excel(request):
    gastos = get_gastos_empresa(request.user)
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin    = request.GET.get('fecha_fin')
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

    headers = ["Fecha", "RUT Emisor", "Folio", "Categoría", "Obra",
               "Monto Neto", "IVA (19%)", "Monto Total", "Usuario"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    total_neto = total_iva = total = 0
    for gasto in gastos:
        ws.append([
            gasto.fecha_emision,
            gasto.rut_emisor or '',
            gasto.folio or '',
            gasto.get_categoria_display(),
            gasto.obra.nombre if gasto.obra else '',
            gasto.monto_neto or 0,
            gasto.iva or 0,
            gasto.monto_total,
            gasto.usuario.username if gasto.usuario else '',
        ])
        total_neto += gasto.monto_neto or 0
        total_iva  += gasto.iva or 0
        total      += gasto.monto_total

    ws.append(["", "", "", "", "TOTALES:", total_neto, total_iva, total, ""])
    for col in [6, 7, 8]:
        ws.cell(row=ws.max_row, column=col).font = Font(bold=True)

    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)

    wb.save(response)
    return response


@login_required
def exportar_pdf(request):
    gastos = get_gastos_empresa(request.user)
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin    = request.GET.get('fecha_fin')
    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)
    gastos = gastos.order_by('-fecha_emision')

    total      = gastos.aggregate(Sum('monto_total'))['monto_total__sum'] or 0
    total_neto = gastos.aggregate(Sum('monto_neto'))['monto_neto__sum']  or 0
    total_iva  = gastos.aggregate(Sum('iva'))['iva__sum']                or 0

    empresa = get_empresa_usuario(request.user)
    context = {
        'gastos': gastos,
        'total': total, 'total_neto': total_neto, 'total_iva': total_iva,
        'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin,
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
                        obra=obra, categoria=codigo,
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
        {'codigo': codigo, 'nombre': nombre,
         'monto_actual': presupuestos_actuales.get(codigo, 0)}
        for codigo, nombre in categorias
    ]
    return render(request, 'gastos/definir_presupuesto.html', {
        'obra': obra, 'datos_tabla': datos_tabla
    })


# =====================================================
# DESCARGA DE BOLETA
# =====================================================
@login_required
def descargar_boleta_pdf(request, pk):
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
# =====================================================
# CURVA S
# =====================================================
@login_required
def curva_s(request, obra_id):
    obra = get_obra_segura_o_404(request.user, obra_id)

    from .models import PlanificacionMensual
    from django.db.models.functions import TruncMonth
    import json
    from datetime import date

    # Gastos reales agrupados por mes
    gastos_reales = (
        Gasto.objects.filter(obra=obra)
        .exclude(fecha_emision__isnull=True)
        .annotate(mes=TruncMonth('fecha_emision'))
        .values('mes')
        .annotate(total=Sum('monto_total'))
        .order_by('mes')
    )

    # Planificación mensual sumada por mes
    planificados = (
        PlanificacionMensual.objects.filter(obra=obra)
        .values('anio', 'mes')
        .annotate(total=Sum('monto_planificado'))
        .order_by('anio', 'mes')
    )

    # Construir meses únicos
    meses_set = set()
    real_dict = {}
    for g in gastos_reales:
        key = g['mes'].strftime('%Y-%m')
        real_dict[key] = g['total']
        meses_set.add(key)

    plan_dict = {}
    for p in planificados:
        key = f"{p['anio']}-{p['mes']:02d}"
        plan_dict[key] = p['total']
        meses_set.add(key)

    meses = sorted(meses_set)

    # Acumular para curva S
    labels, real_acum, plan_acum = [], [], []
    acum_real = acum_plan = 0
    for mes in meses:
        acum_real += real_dict.get(mes, 0)
        acum_plan += plan_dict.get(mes, 0)
        labels.append(mes)
        real_acum.append(acum_real)
        plan_acum.append(acum_plan)

    # Presupuesto total de la obra
    presupuesto_total = Presupuesto.objects.filter(obra=obra).aggregate(
        Sum('monto'))['monto__sum'] or 0

    # Categorías para el formulario de planificación
    categorias = Gasto.CATEGORIAS

    # Guardar planificación si es POST
    if request.method == 'POST':
        anio = int(request.POST.get('anio', date.today().year))
        mes  = int(request.POST.get('mes', date.today().month))
        for codigo, _ in categorias:
            val_str = request.POST.get(f'plan_{codigo}', '0').strip()
            try:
                val = int(val_str) if val_str else 0
                if val >= 0:
                    PlanificacionMensual.objects.update_or_create(
                        obra=obra, anio=anio, mes=mes, categoria=codigo,
                        defaults={'monto_planificado': val}
                    )
            except (ValueError, TypeError):
                pass
        messages.success(request, f"Planificación {mes}/{anio} guardada.")
        return redirect('curva_s', obra_id=obra.id)

    # Planificación existente para el mes/año seleccionado
    anio_sel = int(request.GET.get('anio', date.today().year))
    mes_sel  = int(request.GET.get('mes', date.today().month))
    plan_mes_dict = {
        p.categoria: p.monto_planificado
        for p in PlanificacionMensual.objects.filter(obra=obra, anio=anio_sel, mes=mes_sel)
    }
    # Empaquetar como lista de tuplas (codigo, nombre, monto) — sin filtros personalizados
    categorias_con_plan = [
        (codigo, nombre, plan_mes_dict.get(codigo, 0))
        for codigo, nombre in Gasto.CATEGORIAS
    ]
    meses_nombres = [
        'Enero','Febrero','Marzo','Abril','Mayo','Junio',
        'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'
    ]
    # Lista de (numero, nombre) para el selector de mes
    meses_lista = list(enumerate(meses_nombres, start=1))

    context = {
        'obra': obra,
        'labels': json.dumps(labels),
        'real_acum': json.dumps(real_acum),
        'plan_acum': json.dumps(plan_acum),
        'presupuesto_total': presupuesto_total,
        'gasto_real_total': acum_real,
        'diferencia': presupuesto_total - acum_real,
        'diferencia_abs': abs(presupuesto_total - acum_real),
        'categorias_con_plan': categorias_con_plan,
        'anio_sel': anio_sel,
        'mes_sel': mes_sel,
        'anios': range(date.today().year - 1, date.today().year + 3),
        'meses_lista': meses_lista,
    }
    return render(request, 'gastos/curva_s.html', context)


# =====================================================
# SUBCONTRATOS
# =====================================================
@login_required
def lista_subcontratos(request, obra_id):
    obra = get_obra_segura_o_404(request.user, obra_id)
    from .models import Subcontrato
    subcontratos = Subcontrato.objects.filter(obra=obra)

    total_contratado = subcontratos.aggregate(Sum('monto_contrato'))['monto_contrato__sum'] or 0

    context = {
        'obra': obra,
        'subcontratos': subcontratos,
        'total_contratado': total_contratado,
    }
    return render(request, 'gastos/subcontratos.html', context)


@login_required
def crear_subcontrato(request, obra_id):
    obra = get_obra_segura_o_404(request.user, obra_id)
    from .models import Subcontrato

    if request.method == 'POST':
        try:
            Subcontrato.objects.create(
                obra=obra,
                nombre=request.POST['nombre'],
                rut=request.POST.get('rut') or None,
                descripcion_trabajo=request.POST['descripcion_trabajo'],
                fecha_inicio=request.POST['fecha_inicio'],
                fecha_termino=request.POST.get('fecha_termino') or None,
                monto_contrato=int(request.POST['monto_contrato']),
                estado=request.POST.get('estado', 'ACTIVO'),
                notas=request.POST.get('notas') or None,
                creado_por=request.user,
            )
            messages.success(request, "Subcontrato registrado correctamente.")
            return redirect('lista_subcontratos', obra_id=obra.id)
        except Exception as e:
            messages.error(request, f"Error: {e}")

    context = {
        'obra': obra,
        'estados': [('ACTIVO','En ejecución'),('PAUSADO','Pausado'),
                    ('TERMINADO','Terminado'),('DISPUTA','En disputa')],
    }
    return render(request, 'gastos/crear_subcontrato.html', context)


@login_required
def editar_subcontrato(request, pk):
    from .models import Subcontrato
    sub = get_object_or_404(Subcontrato, pk=pk)
    # Verificar pertenencia
    empresa = get_empresa_usuario(request.user)
    if not request.user.is_superuser and sub.obra.empresa != empresa:
        raise Http404

    if request.method == 'POST':
        sub.nombre              = request.POST['nombre']
        sub.rut                 = request.POST.get('rut') or None
        sub.descripcion_trabajo = request.POST['descripcion_trabajo']
        sub.fecha_inicio        = request.POST['fecha_inicio']
        sub.fecha_termino       = request.POST.get('fecha_termino') or None
        sub.monto_contrato      = int(request.POST['monto_contrato'])
        sub.estado              = request.POST.get('estado', 'ACTIVO')
        sub.notas               = request.POST.get('notas') or None
        sub.save()
        messages.success(request, "Subcontrato actualizado.")
        return redirect('lista_subcontratos', obra_id=sub.obra.id)

    context = {
        'obra': sub.obra,
        'sub': sub,
        'estados': [('ACTIVO','En ejecución'),('PAUSADO','Pausado'),
                    ('TERMINADO','Terminado'),('DISPUTA','En disputa')],
    }
    return render(request, 'gastos/crear_subcontrato.html', context)


# =====================================================
# AVANCE FÍSICO + PROYECCIÓN
# =====================================================
@login_required
def avance_fisico(request, obra_id):
    obra = get_obra_segura_o_404(request.user, obra_id)
    from .models import AvanceFisico
    from datetime import date
    import json

    if request.method == 'POST':
        fecha = request.POST.get('fecha', str(date.today()))
        for codigo, _ in Gasto.CATEGORIAS:
            val_str = request.POST.get(f'avance_{codigo}', '').strip()
            if not val_str:
                continue
            try:
                val = float(val_str)
                val = max(0, min(100, val))
                AvanceFisico.objects.update_or_create(
                    obra=obra, fecha=fecha, categoria=codigo,
                    defaults={
                        'porcentaje_avance': val,
                        'descripcion': request.POST.get(f'obs_{codigo}') or None,
                        'registrado_por': request.user,
                    }
                )
            except (ValueError, TypeError):
                pass
        messages.success(request, f"Avance registrado para {fecha}.")
        return redirect('avance_fisico', obra_id=obra.id)

    # Último avance por categoría
    from django.db.models import Max
    ultimos = {}
    for af in AvanceFisico.objects.filter(obra=obra).order_by('categoria', '-fecha'):
        if af.categoria not in ultimos:
            ultimos[af.categoria] = af

    # Gasto real por categoría
    gastos_cat = {
        g['categoria']: g['total']
        for g in Gasto.objects.filter(obra=obra)
        .values('categoria').annotate(total=Sum('monto_total'))
    }

    # Presupuesto por categoría
    presup_cat = {
        p.categoria: p.monto
        for p in Presupuesto.objects.filter(obra=obra)
    }

    # Construir tabla comparativa + proyección
    tabla = []
    for codigo, nombre in Gasto.CATEGORIAS:
        real   = gastos_cat.get(codigo, 0)
        presup = presup_cat.get(codigo, 0)
        af     = ultimos.get(codigo)
        avance_fis = float(af.porcentaje_avance) if af else 0

        # % financiero = real / presupuesto
        avance_fin = round((real / presup) * 100, 1) if presup > 0 else (100 if real > 0 else 0)

        # Proyección de costo final = real / (avance_fis / 100)
        if avance_fis > 0:
            proyeccion = round(real / (avance_fis / 100))
        elif presup > 0:
            proyeccion = presup
        else:
            proyeccion = real

        desviacion = proyeccion - presup if presup > 0 else 0

        if real > 0 or presup > 0:
            tabla.append({
                'codigo':      codigo,
                'nombre':      nombre,
                'presup':      presup,
                'real':        real,
                'avance_fis':  avance_fis,
                'avance_fin':  avance_fin,
                'proyeccion':  proyeccion,
                'desviacion':     desviacion,
                'desviacion_abs': abs(desviacion),
                'alerta':      'over' if desviacion > 0 else ('warn' if avance_fin > avance_fis + 10 else 'ok'),
                'obs':         af.descripcion if af else '',
                'ultima_fecha': af.fecha if af else None,
            })

    # Histórico de avance para gráfico (última entrada por fecha)
    historico = (
        AvanceFisico.objects.filter(obra=obra)
        .values('fecha')
        .annotate(avg=Avg('porcentaje_avance'))
        .order_by('fecha')
    )
    labels_hist  = [str(h['fecha']) for h in historico]
    data_hist    = [float(h['avg']) for h in historico]

    context = {
        'obra':        obra,
        'tabla':       tabla,
        'labels_hist': json.dumps(labels_hist),
        'data_hist':   json.dumps(data_hist),
        'hoy':         str(date.today()),
        'categorias':  Gasto.CATEGORIAS,
    }
    return render(request, 'gastos/avance_fisico.html', context)