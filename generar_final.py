import pdf417
from PIL import Image, ImageDraw, ImageFont

# Datos reales de una boleta válida
xml_sii = """<TED version="1.0">
  <DD>
    <RE>76123456-7</RE>
    <TD>39</TD>
    <F>123456</F>
    <FE>2026-01-20</FE>
    <MNT>15000</MNT>
  </DD>
</TED>"""

def generar():
    print("Generando código...")
    # Generamos el código PDF417 real
    codes = pdf417.encode(xml_sii, columns=10, security_level=4)
    # Scale 3 es el estándar de impresoras térmicas
    img_codigo = pdf417.render_image(codes, scale=3, ratio=3)
    
    # Lienzo blanco
    ancho, alto = 500, 700
    boleta = Image.new('RGB', (ancho, alto), 'white')
    draw = ImageDraw.Draw(boleta)
    
    # Texto
    draw.text((150, 50), "BOLETA DE PRUEBA", fill="black")
    draw.text((50, 100), "RUT: 76.123.456-7", fill="black")
    draw.text((50, 130), "Monto: $15.000", fill="black")
    draw.text((50, 160), "Fecha: 2026-01-20", fill="black")
    draw.text((50, 400), "Timbre Electrónico SII", fill="gray")
    
    # Pegamos el código ABAJO y CENTRADO
    x = (ancho - img_codigo.width) // 2
    boleta.paste(img_codigo, (x, 420))
    
    nombre = "boleta_oro.png"
    boleta.save(nombre)
    print(f"✅ ¡LISTO! Se creó el archivo: {nombre}")
    print("⚠️ POR FAVOR, SUBE ESTE ARCHIVO ESPECÍFICO A TU WEB ⚠️")

if __name__ == "__main__":
    generar()