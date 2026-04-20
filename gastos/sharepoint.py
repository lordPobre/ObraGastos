import os
import threading
import requests
from django.conf import settings

# --- CONFIGURACIÓN ---
CLIENT_ID = settings.MS_CLIENT_ID
CLIENT_SECRET = settings.MS_CLIENT_SECRET
TENANT_ID = settings.MS_TENANT_ID
SITE_ID = settings.MS_SITE_ID

def obtener_token():
    """Pide a Microsoft un pase temporal (token) de acceso."""
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials',
        'scope': 'https://graph.microsoft.com/.default'
    }
    respuesta = requests.post(url, data=data)
    respuesta.raise_for_status() # Lanza error si algo falla
    return respuesta.json().get('access_token')

def sincronizar_boleta_background(ruta_archivo, nombre_proyecto, nombre_archivo):
    """Sube el archivo a SharePoint por detrás de escena."""
    try:
        token = obtener_token()
        headers = {'Authorization': f'Bearer {token}'}

        # 1. Obtener el "Disco Duro" (Drive) principal de ese sitio SharePoint
        url_drive = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive"
        res_drive = requests.get(url_drive, headers=headers)
        res_drive.raise_for_status()
        drive_id = res_drive.json().get('id')

        # 2. Subir el archivo (¡Magia! Crea las carpetas automáticamente si no existen)
        nombre_carpeta_seguro = nombre_proyecto.replace("/", "-").strip()
        
        # Ruta destino: /ObraGastos_Backups/Edificio Centro/Factura_123.jpg
        url_subida = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/ObraGastos_Backups/{nombre_carpeta_seguro}/{nombre_archivo}:/content"
        )

        # Leemos la foto de la boleta de tu disco
        with open(ruta_archivo, 'rb') as archivo:
            datos_archivo = archivo.read()

        # Enviamos el archivo a Microsoft
        headers_subida = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/octet-stream'
        }
        res_subida = requests.put(url_subida, headers=headers_subida, data=datos_archivo)
        res_subida.raise_for_status()
        
        print(f"✅ Éxito: Boleta respaldada en SharePoint -> {nombre_proyecto}/{nombre_archivo}")

    except Exception as e:
        print(f"❌ Error subiendo a SharePoint: {str(e)}")


def respaldar_en_sharepoint(gasto):
    print(f"▶️ [SHAREPOINT] Evaluando gasto #{gasto.id}...")

    if not gasto.imagen or not hasattr(gasto.imagen, 'path'):
        print("⏸️ [SHAREPOINT] Cancelado: El gasto no tiene un archivo adjunto.")
        return 
        
    if not gasto.obra:
        print("⏸️ [SHAREPOINT] Cancelado: El usuario no seleccionó ninguna Obra/Proyecto.")
        return 
        
    ruta_absoluta = gasto.imagen.path
    nombre_proyecto = gasto.obra.nombre
    
    extension = os.path.splitext(ruta_absoluta)[1]
    nombre_archivo = f"Doc_{gasto.folio or 'SF'}_{gasto.rut_emisor or 'SinRut'}{extension}"

    print(f"🚀 [SHAREPOINT] Todo listo. Subiendo '{nombre_archivo}' a la carpeta '{nombre_proyecto}'...")

    hilo = threading.Thread(
        target=sincronizar_boleta_background, 
        args=(ruta_absoluta, nombre_proyecto, nombre_archivo)
    )
    hilo.start()