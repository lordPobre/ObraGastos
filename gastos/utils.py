"""
Motor de lectura de boletas y facturas chilenas.

ESTRATEGIA EN CASCADA:
1. PDF417 mejorado (código de barras DTE) — datos exactos del SII en XML
   Intenta con múltiples variantes: escala de grises, nitidez, alto contraste,
   upscale 2x, y 4 ángulos de rotación.
2. Tesseract OCR — fallback para boletas sin barcode legible.
   Compatible con Python 3.13 en Windows. ~30 MB RAM. Muy rápido.
3. Validación SII (opcional) — valida DTE contra el endpoint público del SII

INSTALACIÓN EN WINDOWS:
    1. Descargar e instalar Tesseract desde:
       https://github.com/UB-Mannheim/tesseract/wiki
       (elegir "tesseract-ocr-w64-setup-5.x.x.exe")
    2. Durante la instalación, marcar "Spanish" en los idiomas adicionales.
    3. Instalar el wrapper de Python:
       pip install pytesseract
    4. Verificar que TESSERACT_PATH en este archivo apunte a tu instalación.
"""
import os
import re
import logging
from datetime import datetime
from itertools import cycle

import zxingcpp
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
import cv2
import fitz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesseract — compatible con Python 3.13 en Windows, ~30 MB RAM.
# Ajusta esta ruta si instalaste Tesseract en otro directorio.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Tesseract — la ruta se configura en settings.py
# En Windows: C:\Program Files\Tesseract-OCR\tesseract.exe
# En Railway (Linux): /usr/bin/tesseract  (instalado vía nixpacks.toml)
# ---------------------------------------------------------------------------
def _get_tesseract_path():
    """Lee la ruta de Tesseract desde Django settings o usa el default del OS."""
    try:
        from django.conf import settings
        return getattr(settings, 'TESSERACT_CMD', None)
    except Exception:
        return None


def _get_ocr_reader():
    """Configura pytesseract apuntando al ejecutable de Tesseract."""
    try:
        import pytesseract
        ruta = _get_tesseract_path()
        if ruta and os.path.exists(ruta):
            pytesseract.pytesseract.tesseract_cmd = ruta
        return pytesseract
    except ImportError:
        logger.error(
            "pytesseract no está instalado. "
            "Ejecuta: pip install pytesseract  "
            "y descarga Tesseract desde https://github.com/UB-Mannheim/tesseract/wiki"
        )
        raise


# --- VALIDACIONES MATEMÁTICAS ---
def es_rut_valido(rut_str):
    """Retorna True si el string es matemáticamente un RUT chileno válido (módulo 11)."""
    if not rut_str:
        return False
    limpio = str(rut_str).upper().replace(".", "").replace(" ", "").replace("-", "")
    if len(limpio) < 7 or len(limpio) > 10:
        return False
    cuerpo = limpio[:-1]
    dv_usuario = limpio[-1]
    try:
        if not cuerpo.isdigit():
            return False
        reverso = map(int, reversed(cuerpo))
        factores = cycle(range(2, 8))
        s = sum(d * f for d, f in zip(reverso, factores))
        res = (-s) % 11
        if res == 10:
            dv_calculado = "K"
        elif res == 11:
            dv_calculado = "0"
        else:
            dv_calculado = str(res)
        return dv_usuario == dv_calculado
    except Exception:
        return False


def formatear_rut(rut_str):
    """Limpia un RUT al formato 12345678-9 estándar."""
    if not rut_str:
        return None
    limpio = str(rut_str).upper().replace(".", "").replace(" ", "").replace("-", "")
    if len(limpio) < 2:
        return None
    return f"{limpio[:-1]}-{limpio[-1]}"


def limpiar_con_filtro_verde(pil_image):
    """Aplica filtro adaptativo sobre el canal verde — útil para boletas térmicas decoloradas."""
    img_np = np.array(pil_image)
    if len(img_np.shape) < 3:
        return pil_image
    canal_verde = img_np[:, :, 1]
    img_clean = cv2.adaptiveThreshold(
        canal_verde, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return Image.fromarray(img_clean)


def _preprocesar_para_ocr(pil_image):
    """
    Preprocesa una imagen para maximizar la exactitud de PaddleOCR.
    Corrige sombras, bajo contraste y boletas térmicas decoloradas.
    Retorna imagen PIL lista para pasar a PaddleOCR.
    """
    img_np = np.array(pil_image.convert('RGB'))

    # 1. Escala de grises
    gris = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 2. Eliminar sombras mediante división por blur (normalización local)
    #    Especialmente útil en fotos de celular con iluminación desigual
    blur = cv2.GaussianBlur(gris, (21, 21), 0)
    sin_sombra = cv2.divide(gris, blur, scale=255)

    # 3. Binarización adaptativa (mejor que Otsu para boletas térmicas y fotos)
    binarizada = cv2.adaptiveThreshold(
        sin_sombra, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10
    )

    # 4. Convertir de vuelta a RGB (PaddleOCR acepta tanto grises como RGB)
    resultado = cv2.cvtColor(binarizada, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(resultado)


def _cargar_paginas_pdf(ruta_archivo, max_paginas=3):
    """Carga hasta N páginas de un PDF como imágenes PIL en alta resolución."""
    paginas = []
    try:
        doc = fitz.open(ruta_archivo)
        total = min(doc.page_count, max_paginas)
        for i in range(total):
            page = doc.load_page(i)
            # 5x para garantizar que el PDF417 sea legible (antes era 3x)
            pix = page.get_pixmap(matrix=fitz.Matrix(5, 5))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            paginas.append(img)
        doc.close()
    except Exception as e:
        logger.warning(f"Error abriendo PDF {ruta_archivo}: {e}")
    return paginas


def _intentar_leer_barcode(img_pil):
    """
    Intenta leer el PDF417 con 6 variantes de preprocesamiento + 4 ángulos.
    """
    from PIL import ImageOps
    gris = img_pil.convert('L')
    variantes = [
        gris,
        gris.filter(ImageFilter.SHARPEN),
        ImageEnhance.Contrast(img_pil).enhance(2.0).convert('L'),
        gris.resize((gris.width * 2, gris.height * 2), Image.LANCZOS),
        limpiar_con_filtro_verde(img_pil),
        ImageOps.invert(gris),  # invertido — útil en PDFs digitales oscuros
    ]
    for img_trabajo in variantes:
        for angulo in [0, 90, 180, 270]:
            img_rot = img_trabajo.rotate(angulo, expand=True, fillcolor='white') if angulo else img_trabajo
            try:
                res = zxingcpp.read_barcodes(
                    img_rot,
                    formats=zxingcpp.BarcodeFormat.PDF417,
                    try_rotate=True,
                )
                if res and res[0].text:
                    return res[0].text
            except Exception:
                pass
    return None


def _parsear_xml_ted(texto_codigo):
    """
    Parsea el XML TED del DTE chileno y extrae datos del bloque <DD>.

    Estructura estándar del TED (SII):
      <TED><DD>
        <RE>76415882-2</RE>    ← RUT emisor
        <TD>39</TD>            ← Tipo DTE
        <F>7171370</F>         ← Folio
        <FE>2026-01-13</FE>    ← Fecha emisión
        <RR>66666666-6</RR>    ← RUT receptor (NO es el emisor)
        <MNT>56350</MNT>       ← Monto total
      </DD></TED>

    Usa lxml en modo XML (case-sensitive) para evitar que html.parser
    mezcle tags cortos como <F>, <RE>, <RR> entre sí.
    """
    # Extraer solo el bloque TED
    match = re.search(r'<TED[\s\S]*?</TED>', texto_codigo, re.DOTALL)
    xml = match.group(0) if match else texto_codigo

    # Intentar con lxml (case-sensitive, más preciso)
    try:
        from bs4 import BeautifulSoup as BS
        soup = BS(xml, "lxml-xml")
        dd = soup.find("DD")
        if not dd:
            raise ValueError("Sin bloque DD")

        def get_tag(tag):
            """Busca SOLO dentro de <DD>, case-sensitive."""
            node = dd.find(tag)
            return node.get_text(strip=True) if node else None

        return {
            "rut_emisor":    get_tag("RE"),
            "fecha_emision": get_tag("FE"),
            "monto_total":   get_tag("MNT"),
            "folio":         get_tag("F"),
        }

    except Exception:
        # Fallback: regex directo sobre el XML (evita dependencia de parser)
        def regex_tag(tag):
            m = re.search(rf'<{tag}>\s*([^<]+?)\s*</{tag}>', xml, re.IGNORECASE)
            return m.group(1).strip() if m else None

        # Para tags ambiguos (<F> puede estar en varios contextos),
        # buscamos explícitamente dentro de <DD>...</DD>
        dd_match = re.search(r'<DD>([\s\S]*?)</DD>', xml, re.IGNORECASE)
        dd_text = dd_match.group(1) if dd_match else xml

        def regex_dd(tag):
            m = re.search(rf'<{tag}>\s*([^<]+?)\s*</{tag}>', dd_text, re.IGNORECASE)
            return m.group(1).strip() if m else None

        return {
            "rut_emisor":    regex_dd("RE"),
            "fecha_emision": regex_dd("FE"),
            "monto_total":   regex_dd("MNT"),
            "folio":         regex_dd("F"),
        }


def _extraer_monto_total(texto_completo, palabras_ocr, rut_emisor=None):
    """
    Extrae el monto total usando estrategia híbrida:
    1. Buscar palabras clave (TOTAL, MONTO TOTAL, etc.) y tomar el número cercano
    2. Si no hay clave, fallback al máximo de los números válidos
    """
    palabras_clave_total = [
        'TOTALAPAGAR', 'TOTAL APAGAR', 'TOTALPAGAR', 'TOTAL A PAGAR',
        'MONTOTOTAL', 'MONTO TOTAL', 'TOTALNETO', 'TOTAL NETO',
        'TOTAL', 'MONTO', 'PAGAR'
    ]

    rut_numeros = None
    if rut_emisor:
        rut_numeros = rut_emisor.replace("-", "").replace(".", "").replace(" ", "")[:-1]

    # ESTRATEGIA 1: Por palabras clave
    candidatos_por_clave = []
    for i, palabra in enumerate(palabras_ocr):
        p_norm = re.sub(r'[^\w]', '', palabra).upper()
        if not any(clave.replace(' ', '') in p_norm for clave in palabras_clave_total):
            continue

        # Miramos las siguientes 5 palabras para encontrar el número
        for offset in range(1, 6):
            if i + offset >= len(palabras_ocr):
                break
            candidato_raw = palabras_ocr[i + offset]
            # Buscar patrones tipo "1.234.567" o "1234567"
            match = re.search(r'(\d{1,3}(?:[.\s]\d{3})+|\d{4,9})', candidato_raw)
            if match:
                try:
                    val = int(match.group(1).replace('.', '').replace(' ', ''))
                    if 100 < val < 1_000_000_000 and val not in (2024, 2025, 2026, 2027, 2028):
                        if rut_numeros and str(val) == rut_numeros:
                            continue
                        candidatos_por_clave.append(val)
                        break
                except ValueError:
                    continue

    if candidatos_por_clave:
        # El más alto entre los que vienen tras palabras clave (suele ser TOTAL)
        return max(candidatos_por_clave)

    # ESTRATEGIA 2: Fallback al máximo razonable
    posibles = []
    matches = re.findall(r'\b(\d{1,3}(?:\.\d{3})+)\b', texto_completo)
    for m in matches:
        try:
            val = int(m.replace('.', ''))
            if 100 < val < 100_000_000 and val not in (2024, 2025, 2026, 2027, 2028):
                if rut_numeros and str(val) == rut_numeros:
                    continue
                # Filtrar si está seguido de "-" (es parte de un RUT)
                patron_es_rut = re.escape(m) + r"\s*[-]"
                if re.search(patron_es_rut, texto_completo):
                    continue
                posibles.append(val)
        except ValueError:
            continue

    return max(posibles) if posibles else None


def _extraer_folio(palabras_ocr, texto_completo):
    """Extrae el folio sin dañar ceros a la izquierda."""
    claves_folio = ['FOLIO', 'FACTURA', 'ELECTRONICA', 'DOCTO', 'NUMERO', 'BOLETA']

    for i, palabra in enumerate(palabras_ocr):
        p_limpia = re.sub(r'[^\w]', '', palabra).upper()
        if not any(clave in p_limpia for clave in claves_folio):
            continue

        for offset in range(1, 5):
            if i + offset >= len(palabras_ocr):
                break
            candidato_raw = palabras_ocr[i + offset].upper()

            # Filtro 1: ¿Tiene K o guion? (RUT)
            if "K" in candidato_raw or "-" in candidato_raw:
                continue

            # Filtro 2: ¿Es matemáticamente un RUT?
            if es_rut_valido(candidato_raw):
                continue

            candidato_num = re.sub(r'[^\d]', '', candidato_raw)
            if not candidato_num:
                continue

            try:
                val = int(candidato_num)
                if val in (2024, 2025, 2026, 2027, 2028) or val == 0:
                    continue
                if len(candidato_num) > 9:
                    continue
                # IMPORTANTE: devolvemos el string ORIGINAL para preservar ceros a la izquierda
                return candidato_num
            except ValueError:
                continue

    # Fallback regex clásico "N°"
    match_n = re.search(r'N[º°o0\.]\s*[:\.]?\s*(\d{1,10})', texto_completo)
    if match_n:
        posible_folio = match_n.group(1)
        if "-" not in texto_completo[match_n.start():match_n.end() + 2]:
            if "RES" not in texto_completo[max(0, match_n.start() - 10):match_n.start()]:
                return posible_folio

    return None


def _extraer_fecha(texto_completo):
    """Extrae fecha de emisión con año dinámico (no hardcodeado)."""
    anio_actual = datetime.now().year
    anios_validos = [str(y) for y in range(anio_actual - 3, anio_actual + 2)]
    patron_anios = '|'.join(anios_validos)

    # Formato texto: "15 DE MARZO"
    match_txt = re.search(r'(\d{1,2})\s+DE\s+([A-Z]+)', texto_completo)
    if match_txt:
        d, m_txt = match_txt.groups()
        anio = str(anio_actual)
        match_anio = re.search(rf'({patron_anios})', texto_completo)
        if match_anio:
            anio = match_anio.group(1)
        meses = {
            "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
            "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
            "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12"
        }
        m = meses.get(m_txt, "01")
        return f"{anio}-{m}-{d.zfill(2)}"

    # Formato numérico DD-MM-AAAA o DD/MM/AAAA
    match_num = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', texto_completo)
    if match_num:
        d, m, y = match_num.groups()
        if y in anios_validos:
            return f"{y}-{m}-{d}"

    # Formato AAAA-MM-DD
    match_iso = re.search(rf'({patron_anios})[-/](\d{{2}})[-/](\d{{2}})', texto_completo)
    if match_iso:
        y, m, d = match_iso.groups()
        return f"{y}-{m}-{d}"

    return None


def procesar_boleta_chilena(ruta_archivo):
    """
    Procesa una boleta o factura chilena y extrae sus datos.

    Returns:
        dict con keys: rut_emisor, fecha_emision, monto_total, folio, exito, error
    """
    if not os.path.exists(ruta_archivo):
        return {"error": "Archivo no encontrado."}

    logger.info(f"Procesando {ruta_archivo}")
    datos = {
        "rut_emisor": None,
        "fecha_emision": None,
        "monto_total": None,
        "folio": None,
        "exito": False,
        "fuente": None,  # 'barcode' o 'ocr'
    }

    # 1. CARGA (soporte multi-página para PDF)
    paginas = []
    try:
        if ruta_archivo.lower().endswith('.pdf'):
            paginas = _cargar_paginas_pdf(ruta_archivo, max_paginas=3)
            if not paginas:
                return {"error": "No se pudo abrir el PDF."}
        else:
            paginas = [Image.open(ruta_archivo).convert('RGB')]
    except Exception as e:
        return {"error": f"Error abriendo archivo: {e}"}

    # 2. CÓDIGO DE BARRAS (intentar en TODAS las páginas)
    for img_pil in paginas:
        texto_codigo = _intentar_leer_barcode(img_pil)
        if not texto_codigo:
            logger.info(f"Barcode NO encontrado en página {paginas.index(img_pil)+1}, imagen {img_pil.size}")
            continue

        logger.info(f"XML CRUDO DEL BARCODE:\n{texto_codigo}")  # DEBUG

        try:
            xml_data = _parsear_xml_ted(texto_codigo)
            datos.update(xml_data)

            # Validar y formatear RUT
            if datos["rut_emisor"] and not es_rut_valido(datos["rut_emisor"]):
                datos["rut_emisor"] = None
            elif datos["rut_emisor"]:
                datos["rut_emisor"] = formatear_rut(datos["rut_emisor"])

            if datos["rut_emisor"]:
                datos["exito"] = True
                datos["fuente"] = "barcode"
                logger.info(f"Datos extraídos por BARCODE: {datos}")
                return datos
        except Exception as e:
            logger.warning(f"Error parseando XML: {e}")

    # 3. TEXTO EMBEBIDO EN PDF (sin OCR — para PDFs digitales como facturas electrónicas)
    if ruta_archivo.lower().endswith('.pdf'):
        try:
            doc = fitz.open(ruta_archivo)
            texto_pdf = " ".join(page.get_text() for page in doc).upper()
            doc.close()
            if len(texto_pdf.strip()) > 50:  # tiene texto real, no es escaneado
                logger.info("Extrayendo texto embebido del PDF (sin OCR)...")
                resultados = texto_pdf.split()

                if not datos["rut_emisor"]:
                    candidatos = re.findall(
                        r'(?<!\d)(\d{1,2}[\s.]?\d{3}[\s.]?\d{3}\s?[-]\s?[\dkK])',
                        texto_pdf
                    )
                    for c in candidatos:
                        if es_rut_valido(c):
                            rut_fmt = formatear_rut(c)
                            # Ignorar RUT del receptor (66.666.666-6 es el "RUT" de personas sin RUT)
                            if rut_fmt != "66666666-6":
                                datos["rut_emisor"] = rut_fmt
                                break

                if not datos["folio"]:
                    datos["folio"] = _extraer_folio(resultados, texto_pdf)

                if not datos["monto_total"]:
                    datos["monto_total"] = _extraer_monto_total(texto_pdf, resultados, datos.get("rut_emisor"))

                if not datos["fecha_emision"]:
                    datos["fecha_emision"] = _extraer_fecha(texto_pdf)

                if datos["rut_emisor"] or datos["monto_total"]:
                    datos["exito"] = True
                    datos["fuente"] = "texto_pdf"
                    logger.info(f"Datos extraídos de texto PDF: {datos}")
                    return datos
        except Exception as e:
            logger.warning(f"Error extrayendo texto del PDF: {e}")

    # 4. TESSERACT OCR (fallback cuando no hay barcode legible)
    logger.info("Iniciando Tesseract como fallback...")
    try:
        pytesseract = _get_ocr_reader()

        # Preprocesar imagen: eliminar sombras y mejorar contraste
        img_preprocesada = _preprocesar_para_ocr(paginas[0])

        # Tesseract: config optimizada para documentos chilenos (texto impreso)
        config = r'--oem 3 --psm 6 -l spa'
        texto_completo = pytesseract.image_to_string(img_preprocesada, config=config).upper()

        # Convertir texto en lista de palabras (mismo formato que antes)
        resultados = texto_completo.split()

        logger.debug(f"Tesseract raw (primeros 200 chars): {texto_completo[:200]}")

        # A. RUT
        if not datos["rut_emisor"]:
            candidatos = re.findall(
                r'(?<!\d)(\d{1,2}[\s.]?\d{3}[\s.]?\d{3}\s?[-]\s?[\dkK])',
                texto_completo
            )
            for candidato in candidatos:
                if es_rut_valido(candidato):
                    datos["rut_emisor"] = formatear_rut(candidato)
                    break

        # B. FOLIO (sin dañar ceros)
        if not datos["folio"]:
            datos["folio"] = _extraer_folio(resultados, texto_completo)

        # C. MONTO TOTAL (con palabras clave)
        if not datos["monto_total"]:
            datos["monto_total"] = _extraer_monto_total(
                texto_completo, resultados, datos.get("rut_emisor")
            )

        # D. FECHA (año dinámico)
        if not datos["fecha_emision"]:
            datos["fecha_emision"] = _extraer_fecha(texto_completo)

        datos["fuente"] = "ocr"

    except Exception as e:
        logger.error(f"Error en OCR: {e}", exc_info=True)

    if datos["rut_emisor"] or datos["folio"] or datos["monto_total"]:
        datos["exito"] = True
        return datos

    return {"error": "No se pudieron leer los datos."}


def validar_dte_sii(rut_emisor, tipo_dte, folio, fecha_emision, monto_total, rut_receptor=None):
    """
    Valida un DTE consultando el endpoint público del SII.

    Args:
        rut_emisor: "76123456-7"
        tipo_dte: 33 (factura electrónica), 39 (boleta electrónica), etc.
        folio: número del folio
        fecha_emision: "YYYY-MM-DD"
        monto_total: int
        rut_receptor: opcional

    Returns:
        dict con keys: valido (bool), estado (str), mensaje (str)

    NOTA: Esta función requiere conexión a internet y puede ser lenta.
    Llamarla en background o con timeout corto.
    """
    import requests

    if not all([rut_emisor, tipo_dte, folio, fecha_emision, monto_total]):
        return {"valido": False, "estado": "datos_incompletos", "mensaje": "Faltan datos para validar"}

    try:
        rut_clean = rut_emisor.replace(".", "").replace("-", "")
        rut_cuerpo = rut_clean[:-1]
        rut_dv = rut_clean[-1]

        fecha_obj = datetime.strptime(fecha_emision, "%Y-%m-%d")
        fecha_sii = fecha_obj.strftime("%d-%m-%Y")

        url = "https://palena.sii.cl/cgi_dte/UPL/DTEUpload"

        params = {
            "rutEmpresa": rut_cuerpo,
            "dvEmpresa": rut_dv,
            "tipoDoc": tipo_dte,
            "folioDoc": folio,
            "fechaEmis": fecha_sii,
            "montoDoc": monto_total,
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            txt = response.text.upper()
            if "DTE EMITIDO" in txt or "AUTORIZADO" in txt:
                return {"valido": True, "estado": "autorizado", "mensaje": "DTE válido en SII"}
            elif "NO HAY DATOS" in txt or "NO EXISTE" in txt:
                return {"valido": False, "estado": "no_existe", "mensaje": "DTE no registrado en SII"}

        return {"valido": False, "estado": "desconocido", "mensaje": "Respuesta no concluyente del SII"}

    except requests.Timeout:
        return {"valido": False, "estado": "timeout", "mensaje": "SII no respondió a tiempo"}
    except Exception as e:
        logger.warning(f"Error validando con SII: {e}")
        return {"valido": False, "estado": "error", "mensaje": str(e)}