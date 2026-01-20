import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.contrib import messages
from .models import Gasto
from .forms import GastoForm, CargaMasivaForm
from .utils import procesar_boleta_chilena
from datetime import date, datetime 
from django.urls import reverse
from django.utils.http import urlencode
from django.http import HttpResponse
from django.db.models.functions import TruncMonth
from django.template.loader import render_to_string
from xhtml2pdf import pisa

def dashboard(request):
    gastos = Gasto.objects.all().order_by('-fecha_emision')
    obra_id = request.GET.get('obra')
    if obra_id:
        pass 
    resumen_mensual = (
        gastos
        .annotate(mes=TruncMonth('fecha_emision'))
        .values('mes')
        .annotate(total=Sum('monto_total'))
        .order_by('mes')
    )
    labels_grafico = []
    data_grafico = []

    for item in resumen_mensual:
        if item['mes']:
            labels_grafico.append(item['mes'].strftime("%Y-%m"))
            data_grafico.append(item['total'])
    suma_data = gastos.aggregate(Sum('monto_total'))
    total_mes = suma_data['monto_total__sum'] or 0
    cantidad_gastos = gastos.count()
    ultimos_gastos = gastos[:10]

    context = {
        'ultimos_gastos': ultimos_gastos,
        'total_mes': total_mes,
        'cantidad_gastos': cantidad_gastos,
        'fecha_actual': date.today(),
        'obras': [], 
        'obra_seleccionada': obra_id,
        'labels_grafico': labels_grafico,
        'data_grafico': data_grafico,
    }
    
    return render(request, 'gastos/dashboard.html', context)

@login_required 
def crear_gasto(request):
    if request.method == 'POST':
        form = GastoForm(request.POST, request.FILES)
        if form.is_valid():
            gasto = form.save(commit=False) 
            gasto.usuario = request.user 
            gasto.save() 

            
            if gasto.imagen:
                try:
                    # Ajusta 'imagen' o 'imagen_boleta' según tu modelo
                    resultado = procesar_boleta_chilena(gasto.imagen.path)
                    
                    if 'error' not in resultado:
                        # 1. Asignar Monto (Ya lo tenías)
                        if resultado.get('monto_total'):
                            gasto.monto_total = resultado['monto_total']
                        
                        # 2. Asignar RUT (Ya lo tenías)
                        if resultado.get('rut_emisor'):
                            gasto.rut_emisor = resultado['rut_emisor']

                        # 3. --- AGREGAR ESTO (Faltaba esta parte) ---
                        if resultado.get('folio'):
                            gasto.folio = resultado['folio']
                        # --------------------------------------------

                        # 4. Asignar Fecha (Ya lo tenías)
                        fecha_str = resultado.get('fecha_emision')
                        if fecha_str:
                            try:
                                gasto.fecha_emision = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass

                        gasto.procesado_exitosamente = True
                        gasto.save() # Aquí se guardan los cambios en la BD
                        messages.success(request, "¡Boleta leída! Por favor confirma los datos.")
                    else:
                        messages.warning(request, f"Escáner: {resultado['error']}")
                except Exception as e:
                    messages.warning(request, f"Error imagen: {e}")
            
            return redirect('editar_gasto', pk=gasto.pk)
    else:
        form = GastoForm()

    return render(request, 'gastos/crear_gasto.html', {'form': form, 'titulo': 'Nuevo Gasto'})

# --- VISTA 3: EDITAR (VERIFICAR) ---
def editar_gasto(request, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    
    if request.method == 'POST':
        form = GastoForm(request.POST, request.FILES, instance=gasto)
        if form.is_valid():
            form.save()
            messages.success(request, "Gasto verificado y guardado.")
            return redirect('dashboard')
    else:
        form = GastoForm(instance=gasto)

    return render(request, 'gastos/editar_gasto.html', {'form': form})

# --- VISTA 4: ELIMINAR ---
def eliminar_gasto(request, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    if request.method == 'POST':
        gasto.delete()
        messages.success(request, "Gasto eliminado.")
        return redirect('dashboard')
    return render(request, 'gastos/eliminar_gasto.html', {'object': gasto})

def historial_gastos(request):
    # 1. Obtenemos todos los gastos base ordenados por fecha
    gastos = Gasto.objects.all().order_by('-fecha_emision')
    
    # 2. Capturamos los filtros de la URL (si existen)
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    # 3. Aplicamos lógica de filtrado
    if fecha_inicio:
        gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    
    if fecha_fin:
        gastos = gastos.filter(fecha_emision__lte=fecha_fin)

    # 4. Calculamos el total de LO QUE SE ESTÁ VIENDO (filtrado)
    # Esto es muy útil para saber cuánto se gastó en ese rango de fechas específico
    suma_filtrada = gastos.aggregate(Sum('monto_total'))['monto_total__sum'] or 0

    context = {
        'gastos': gastos,
        'total_filtrado': suma_filtrada,
        'fecha_inicio': fecha_inicio, # Para que el input no se borre al buscar
        'fecha_fin': fecha_fin,
    }
    
    return render(request, 'gastos/historial.html', context)

@login_required
def carga_masiva(request):
    if request.method == 'POST':
        print("DEBUG: --- Iniciando Carga Masiva ---")
        
        form = CargaMasivaForm(request.POST, request.FILES)
        
        if form.is_valid():
            # USAMOS getlist PARA OBTENER TODOS LOS ARCHIVOS
            archivos = request.FILES.getlist('imagenes')
            print(f"DEBUG: Se recibieron {len(archivos)} archivos.")
            
            procesados = 0
            fallidos = 0
            
            for f in archivos:
                try:
                    print(f"DEBUG: Procesando archivo: {f.name}")
                    
                    # 1. Crear Gasto Base
                    nuevo_gasto = Gasto(
                        usuario=request.user,
                        imagen=f,
                        procesado_exitosamente=False
                    )
                    nuevo_gasto.save()
                    
                    # 2. Escanear
                    resultado = procesar_boleta_chilena(nuevo_gasto.imagen.path)
                    
                    if 'error' not in resultado:
                        if resultado.get('monto_total'):
                            nuevo_gasto.monto_total = resultado['monto_total']
                        if resultado.get('rut_emisor'):
                            nuevo_gasto.rut_emisor = resultado['rut_emisor']
                        if resultado.get('folio'):
                            nuevo_gasto.folio = resultado['folio']
                        
                        # Fecha
                        fecha_str = resultado.get('fecha_emision')
                        if fecha_str:
                            try:
                                nuevo_gasto.fecha_emision = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                            except ValueError: pass
                        
                        nuevo_gasto.procesado_exitosamente = True
                        nuevo_gasto.save()
                        procesados += 1
                    else:
                        print(f"DEBUG: Falló lectura de {f.name}: {resultado['error']}")
                        fallidos += 1
                        
                except Exception as e:
                    print(f"DEBUG: Error crítico en {f.name}: {e}")
                    fallidos += 1

            # Mensajes al usuario
            if procesados > 0:
                messages.success(request, f"¡Éxito! {procesados} boletas procesadas correctamente.")
            if fallidos > 0:
                messages.warning(request, f"{fallidos} boletas no se pudieron leer. Revísalas en el historial.")
            
            return redirect('historial_gastos')
        
        else:
            print("DEBUG: Formulario inválido. Errores:")
            print(form.errors)
            messages.error(request, "Error en el formulario. Revisa la consola.")
    
    else:
        form = CargaMasivaForm()

    return render(request, 'gastos/carga_masiva.html', {'form': form})

@login_required
def eliminar_masivo(request):
    if request.method == 'POST':
        ids_a_borrar = request.POST.getlist('gastos_ids')
        
        # --- Lógica de Borrado (Igual que antes) ---
        if ids_a_borrar:
            cantidad, _ = Gasto.objects.filter(
                id__in=ids_a_borrar, 
                usuario=request.user
            ).delete()
            
            if cantidad > 0:
                messages.success(request, f"🗑️ Se eliminaron {cantidad} boletas.")
            else:
                messages.warning(request, "No se pudo eliminar.")
        
        # --- NUEVA LÓGICA DE REDIRECCIÓN INTELIGENTE ---
        
        # 1. Recuperamos los filtros que venían ocultos en el formulario
        f_inicio = request.POST.get('fecha_inicio_filtro')
        f_fin = request.POST.get('fecha_fin_filtro')
        
        # 2. Obtenemos la URL base del historial (ej: '/gastos/historial/')
        base_url = reverse('historial_gastos')
        
        # 3. Preparamos los parámetros (query string)
        parametros = {}
        if f_inicio: parametros['fecha_inicio'] = f_inicio
        if f_fin:    parametros['fecha_fin'] = f_fin
        
        # 4. Si hay parámetros, los pegamos a la URL
        if parametros:
            # Esto crea algo como: /gastos/historial/?fecha_inicio=2024-01-01&fecha_fin=...
            url_final = f"{base_url}?{urlencode(parametros)}"
            return redirect(url_final)
            
    # Si no hay filtros, volvemos al historial normal
    return redirect('historial_gastos')

@login_required
def exportar_excel(request):
    # 1. Recuperar Filtros (Igual que en el historial)
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    
    gastos = Gasto.objects.all().order_by('-fecha_emision')
    if fecha_inicio: gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:    gastos = gastos.filter(fecha_emision__lte=fecha_fin)

    # 2. Configurar el Excel
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=Reporte_Gastos_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gastos"

    # 3. Estilos
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    
    # 4. Cabecera
    headers = ["Fecha", "RUT Emisor", "Folio", "Monto Total", "Usuario"]
    ws.append(headers)
    
    for cell in ws[1]: # Aplicar estilo a la primera fila
        cell.font = header_font
        cell.fill = header_fill

    # 5. Datos
    total = 0
    for gasto in gastos:
        ws.append([
            gasto.fecha_emision,
            gasto.rut_emisor,
            gasto.folio,
            gasto.monto_total,
            gasto.usuario.username
        ])
        total += gasto.monto_total

    # 6. Fila de Total
    ws.append(["", "", "TOTAL ACUMULADO:", total, ""])
    ws.cell(row=ws.max_row, column=4).font = Font(bold=True)

    wb.save(response)
    return response

@login_required
def exportar_pdf(request):
    # 1. Recuperar Filtros
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    
    gastos = Gasto.objects.all().order_by('-fecha_emision')
    if fecha_inicio: gastos = gastos.filter(fecha_emision__gte=fecha_inicio)
    if fecha_fin:    gastos = gastos.filter(fecha_emision__lte=fecha_fin)
    
    total = gastos.aggregate(Sum('monto_total'))['monto_total__sum'] or 0

    # 2. Renderizar HTML para el PDF
    template_path = 'gastos/reporte_pdf.html'
    context = {
        'gastos': gastos,
        'total': total,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'empresa': 'Mi Constructora S.A.' # Puedes personalizar esto
    }
    
    # 3. Crear PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_gastos.pdf"'
    
    html = render_to_string(template_path, context)
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Tuvimos errores generando el PDF <pre>' + html + '</pre>')
    return response