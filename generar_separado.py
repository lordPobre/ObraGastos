import pdf417
from PIL import Image, ImageDraw, ImageFont

xml_sii = """<TED version="1.0"><DD><RE>76123456-7</RE><TD>39</TD><F>123456</F><FE>2026-01-20</FE><MNT>15000</MNT></DD></TED>"""

def generar():
    # Usamos scale=2 (Más pequeño y nítido para escáneres)
    codes = pdf417.encode(xml_sii, columns=10, security_level=4)
    img_codigo = pdf417.render_image(codes, scale=2, ratio=3)
    
    ancho, alto = 500, 800
    boleta = Image.new('RGB', (ancho, alto), 'white')
    draw = ImageDraw.Draw(boleta)
    
    # Texto MUY ARRIBA
    draw.text((50, 100), "BOLETA DE PRUEBA", fill="black")
    draw.text((50, 200), "Timbre Electrónico SII", fill="gray")
    
    # Código MUY ABAJO (Y=500), con 300px de aire
    x = (ancho - img_codigo.width) // 2
    boleta.paste(img_codigo, (x, 500))
    
    nombre = "boleta_separada.png"
    boleta.save(nombre)
    print(f"✅ Creado: {nombre}")

if __name__ == "__main__":
    generar()