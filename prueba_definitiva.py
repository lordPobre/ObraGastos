import zxingcpp
import pdf417
from PIL import Image, ImageDraw, ImageFont, ImageOps

# 1. GENERAMOS LA IMAGEN (A prueba de tontos)
print("--- 1. GENERANDO IMAGEN ---")
datos = "<TED><DD><RE>99999999-9</RE><MNT>10000</MNT></DD></TED>"
# Usamos scale=4 (Píxeles enteros, fácil de leer) y columnas=10 (Más angosto)
codes = pdf417.encode(datos, columns=10, security_level=3)
img_codigo = pdf417.render_image(codes, scale=4, ratio=3)

lienzo = Image.new('RGB', (600, 800), 'white')
draw = ImageDraw.Draw(lienzo)
draw.text((100, 100), "TEXTO MOLESTO QUE CONFUNDE AL LECTOR", fill="black")
# Pegamos el código ABAJO (Y=500)
lienzo.paste(img_codigo, (100, 500))
lienzo.save("test_debug.png")
print("✅ Imagen 'test_debug.png' generada.")

# 2. INTENTAMOS LEERLA (Simulando el servidor)
print("\n--- 2. INTENTANDO LEER ---")
img = Image.open("test_debug.png").convert('L') # Convertir a grises

# A) INTENTO DIRECTO (Fallará por el texto)
res = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.PDF417, is_pure=True)
print(f"A) Lectura Directa (Pure): {'✅ ÉXITO' if res else '❌ FALLÓ (Culpa del texto)'}")

# B) INTENTO CON RECORTE (La solución)
ancho, alto = img.size
# Cortamos desde la mitad (400px) hasta el final. Eliminamos el texto de arriba.
img_recorte = img.crop((0, 400, ancho, alto))
img_recorte.save("test_recorte_debug.png") # Para que veas qué estamos leyendo

res_b = zxingcpp.read_barcodes(img_recorte, formats=zxingcpp.BarcodeFormat.PDF417, is_pure=True)
if res_b:
    print(f"B) Lectura con Recorte + Pure: ✅ ÉXITO -> {res_b[0].text}")
else:
    print(f"B) Lectura con Recorte + Pure: ❌ FALLÓ")

# C) INTENTO MOTOR B (PDF417Decoder)
try:
    from pdf417decoder import PDF417Decoder
    decoder = PDF417Decoder(img_recorte)
    if decoder.decode() > 0:
         print(f"C) Motor B (PDF417Decoder): ✅ ÉXITO -> {decoder.barcode_data_index_to_string(0)}")
    else:
         print(f"C) Motor B (PDF417Decoder): ❌ FALLÓ")
except:
    print("C) Motor B no instalado.")