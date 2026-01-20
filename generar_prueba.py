from pdf417gen import encode, render_image
from PIL import Image, ImageDraw, ImageFont

# 1. Datos simulados (Formato XML del SII)
# Este contenido es texto válido que tu escáner DEBERÍA leer.
contenido_xml = """<TED version="1.0">
  <DD>
    <RE>77.777.777-0</RE>
    <TD>33</TD>
    <F>1</F>
    <FE>2026-01-15</FE>
    <RR>66666666-6</RR>
    <RSR>JUAN PEREZ</RSR>
    <MNT>15000</MNT>
    <IT1>Prueba de Escaner</IT1>
  </DD>
  <FRMT algorithm="SHA1withRSA">firma_falsa_para_rellenar</FRMT>
</TED>"""

print("Generando código PDF417...")

# 2. Generar el Código de Barras
# columns=6 define el ancho (cantidad de columnas de datos)
codigos = encode(contenido_xml, columns=6, security_level=5)

# Renderizar a imagen
# scale=3: Hace los píxeles más grandes (zoom)
# ratio=3: Hace las barras más altas (estilo boleta)
img_codigo = render_image(codigos, scale=3, ratio=3)

# 3. Crear la Imagen de la Boleta (Lienzo blanco)
ancho_boleta = 600
alto_boleta = 800
boleta = Image.new('RGB', (ancho_boleta, alto_boleta), 'white')
draw = ImageDraw.Draw(boleta)

# Intentamos cargar fuentes, si no, usa la por defecto
try:
    font = ImageFont.truetype("arial.ttf", 20)
    font_bold = ImageFont.truetype("arialbd.ttf", 24)
except:
    font = ImageFont.load_default()
    font_bold = ImageFont.load_default()

# 4. Dibujar Texto para que parezca real
draw.text((50, 50), "EMPRESA DE PRUEBA SPA", fill='red', font=font_bold)
draw.text((50, 90), "RUT: 77.777.777-0", fill='black', font=font)
draw.text((50, 120), "Giro: PRUEBAS DE SOFTWARE", fill='black', font=font)

draw.text((350, 50), "BOLETA N° 1", fill='red', font=font_bold)
draw.text((50, 200), "Fecha: 2026-01-15", fill='black', font=font)
draw.text((50, 240), "Total: $15.000", fill='black', font=font_bold)

# 5. Pegar el código PDF417 generado
# Centramos el código en la parte inferior
pos_x = (ancho_boleta - img_codigo.width) // 2
pos_y = 350
boleta.paste(img_codigo, (pos_x, pos_y))

# 6. Guardar archivo final
nombre_archivo = "boleta_perfecta_para_pruebas.png"
boleta.save(nombre_archivo)

print(f"¡LISTO! Imagen generada: {nombre_archivo}")
print("Sube esta imagen a tu sistema Django.")