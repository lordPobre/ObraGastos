import zxingcpp
from PIL import Image
import numpy as np 
import easyocr 
import cv2 
import os
import re
import fitz 
from bs4 import BeautifulSoup
from itertools import cycle 

# --- INICIALIZACIÓN ---
reader = easyocr.Reader(['es'], gpu=False) 

try:
    from pdf417decoder import PDF417Decoder
    TIENE_MOTOR_B = True
except ImportError:
    TIENE_MOTOR_B = False

# --- VALIDACIONES MATEMÁTICAS ---
def es_rut_valido(rut_str):
    """Retorna True si el string es matemáticamente un RUT chileno."""
    limpio = rut_str.upper().replace(".", "").replace(" ", "").replace("-", "")
    if len(limpio) < 7 or len(limpio) > 10: return False
    cuerpo = limpio[:-1]
    dv_usuario = limpio[-1]
    try:
        reverso = map(int, reversed(str(cuerpo)))
        factores = cycle(range(2, 8))
        s = sum(d * f for d, f in zip(reverso, factores))
        res = (-s) % 11
        if res == 10: dv_calculado = "K"
        elif res == 11: dv_calculado = "0"
        else: dv_calculado = str(res)
        return dv_usuario == dv_calculado
    except: return False

def limpiar_con_filtro_verde(pil_image):
    img_np = np.array(pil_image)
    if len(img_np.shape) < 3: return pil_image
    canal_verde = img_np[:, :, 1]
    img_clean = cv2.adaptiveThreshold(
        canal_verde, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15  
    )
    return Image.fromarray(img_clean)

def procesar_boleta_chilena(ruta_archivo):
    if not os.path.exists(ruta_archivo): return {"error": "Archivo no encontrado."}

    print(f"DEBUG: Procesando {ruta_archivo}...")
    datos = {"rut_emisor": None, "fecha_emision": None, "monto_total": None, "folio": None, "exito": False}

    # 1. CARGA
    img_pil = None
    try:
        if ruta_archivo.lower().endswith('.pdf'):
            doc = fitz.open(ruta_archivo)
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img_pil = Image.open(ruta_archivo).convert('RGB')
    except Exception as e:
        return {"error": f"Error archivo: {e}"}

    # 2. CÓDIGO DE BARRAS
    img_limpia = limpiar_con_filtro_verde(img_pil)
    texto_codigo = None
    for img_trabajo in [img_pil.convert('L'), img_limpia]:
        if texto_codigo: break
        for angulo in [0, 90, 270]:
            if texto_codigo: break
            img_rot = img_trabajo.rotate(angulo, expand=True, fillcolor='white') if angulo != 0 else img_trabajo
            try:
                res = zxingcpp.read_barcodes(img_rot, formats=zxingcpp.BarcodeFormat.PDF417, try_rotate=True)
                if res and res[0].text:
                    texto_codigo = res[0].text
                    break
            except: pass

    if texto_codigo:
        match = re.search(r'<TED.*?</TED>', texto_codigo, re.DOTALL)
        xml = match.group(0) if match else texto_codigo
        soup = BeautifulSoup(xml, "html.parser")
        def get_xml(tags):
            for t in tags:
                n = soup.find(t) or soup.find(t.upper())
                if n: return n.text.strip()
            return None
        
        datos["rut_emisor"] = get_xml(["RE", "RUTEmisor"])
        datos["fecha_emision"] = get_xml(["FE", "FchEmis"])
        datos["monto_total"] = get_xml(["MNT", "MntTotal"])
        datos["folio"] = get_xml(["F", "Folio"])
        
        if datos["rut_emisor"] and not es_rut_valido(datos["rut_emisor"]):
             datos["rut_emisor"] = None 
        
        if datos["rut_emisor"]: 
            datos["exito"] = True
            return datos

    # 3. IA EASYOCR
    print("DEBUG: Iniciando IA EasyOCR...")
    try:
        img_np = np.array(img_limpia)
        resultados = reader.readtext(img_np, detail=0)
        texto_completo = " ".join(resultados).upper()
        
        print(f"DEBUG TEXTO RAW: {texto_completo[:100]}...")

        # --- A. RUT ---
        if not datos["rut_emisor"]:
            candidatos = re.findall(r'(?<!\d)(\d{1,2}[\s.]?\d{3}[\s.]?\d{3}\s?[-]\s?[\dkK])', texto_completo)
            for candidato in candidatos:
                if es_rut_valido(candidato):
                    datos["rut_emisor"] = candidato.replace(" ", "").replace(".", "")
                    break 

        # --- B. FOLIO (CON FILTRO ANTI-RUT) ---
        if not datos["folio"]:
            claves_folio = ['FOLIO', 'FACTURA', 'ELECTRONICA', 'DOCTO', 'N', 'NO', 'NUMERO']
            
            for i, palabra in enumerate(resultados):
                p_limpia = re.sub(r'[^\w]', '', palabra).upper()
                
                if any(clave in p_limpia for clave in claves_folio):
                    
                    # Miramos las siguientes 4 palabras
                    for offset in range(1, 5): 
                        if i + offset >= len(resultados): break
                        
                        candidato_raw = resultados[i+offset].upper()
                        
                        # --- FILTRO 1: ¿Parece un RUT? (Tiene K o Guion) ---
                        if "K" in candidato_raw or "-" in candidato_raw:
                            continue # Si tiene K o -, es un RUT, ignorar.

                        # --- FILTRO 2: ¿Es matemáticamente un RUT? ---
                        if es_rut_valido(candidato_raw):
                            continue # Si pasa la validación de RUT, es un RUT, ignorar.

                        # Limpiamos para obtener solo números
                        candidato_num = re.sub(r'[^\d]', '', candidato_raw)
                        
                        if len(candidato_num) > 0:
                            val = int(candidato_num)
                            
                            # Filtros de seguridad
                            if val in [2024, 2025, 2026]: continue # Año
                            if val == 0: continue
                            if len(candidato_num) > 9: continue # Muy largo
                            
                            datos["folio"] = str(val)
                            print(f"DEBUG: Folio encontrado: {val}")
                            break
                    
                    if datos["folio"]: break
            
            # Respaldo Regex Clásico "N°"
            if not datos["folio"]:
                match_n = re.search(r'N[º°o0\.]\s*[:\.]?\s*(\d{1,10})', texto_completo)
                if match_n:
                    # Validar que lo encontrado NO sea un RUT
                    posible_folio = match_n.group(1)
                    contexto_completo = texto_completo[match_n.start():match_n.end()+2] # Miramos un poco adelante
                    
                    if "-" not in contexto_completo and "RES" not in texto_completo[max(0, match_n.start()-10):match_n.start()]:
                         datos["folio"] = posible_folio

        # --- C. TOTAL ---
        if not datos["monto_total"]:
            posibles_montos = []
            matches = re.findall(r'\b(\d{1,3}(?:\.\d{3})+)\b', texto_completo)
            for m in matches:
                try:
                    val = int(m.replace('.', ''))
                    if 100 < val < 100000000 and val not in [2024, 2025, 2026]:
                        if datos["rut_emisor"]:
                            rut_numeros = datos["rut_emisor"].split("-")[0]
                            if str(val) == rut_numeros: continue 
                        
                        patron_es_rut = re.escape(m) + r"\s*[-]"
                        if re.search(patron_es_rut, texto_completo): continue
                        
                        posibles_montos.append(val)
                except: pass
            
            if posibles_montos:
                datos["monto_total"] = str(max(posibles_montos))

        # --- D. FECHA ---
        if not datos["fecha_emision"]:
            match_txt = re.search(r'(\d{1,2})\s+DE\s+([A-Z]+)', texto_completo)
            if match_txt:
                d, m_txt = match_txt.groups()
                anio = "2026"
                match_anio = re.search(r'(202[4-6])', texto_completo)
                if match_anio: anio = match_anio.group(1)
                meses = {"ENERO":"01", "FEBRERO":"02", "MARZO":"03", "ABRIL":"04", "MAYO":"05", "JUNIO":"06",
                         "JULIO":"07", "AGOSTO":"08", "SEPTIEMBRE":"09", "OCTUBRE":"10", "NOVIEMBRE":"11", "DICIEMBRE":"12"}
                m = meses.get(m_txt, "01")
                datos["fecha_emision"] = f"{anio}-{m}-{d.zfill(2)}"
            else:
                match_num = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', texto_completo)
                if match_num:
                    d, m, y = match_num.groups()
                    datos["fecha_emision"] = f"{y}-{m}-{d}"

    except Exception as e:
        print(f"DEBUG ERROR IA: {e}")

    if datos["folio"]:
        try: datos["folio"] = str(int(datos["folio"]))
        except: pass
    
    if datos["rut_emisor"] or datos["folio"] or datos["monto_total"]:
        datos["exito"] = True
        return datos
    else:
        return {"error": "No se pudieron leer los datos."}