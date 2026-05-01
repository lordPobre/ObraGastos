"""
Respaldo de boletas en SharePoint via Microsoft Graph API.

CORRECCIONES:
- Logging en vez de print()
- Timeouts en todas las requests
- Manejo robusto de errores
- Validación de configuración antes de intentar
"""
import os
import threading
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _config_valida():
    """Verifica que las credenciales de Microsoft estén configuradas."""
    return all([
        getattr(settings, 'MS_CLIENT_ID', None),
        getattr(settings, 'MS_CLIENT_SECRET', None),
        getattr(settings, 'MS_TENANT_ID', None),
        getattr(settings, 'MS_SITE_ID', None),
    ])


def obtener_token():
    """Pide un token de acceso a Microsoft Identity Platform."""
    url = f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}/oauth2/v2.0/token"
    data = {
        'client_id': settings.MS_CLIENT_ID,
        'client_secret': settings.MS_CLIENT_SECRET,
        'grant_type': 'client_credentials',
        'scope': 'https://graph.microsoft.com/.default'
    }
    respuesta = requests.post(url, data=data, timeout=15)
    respuesta.raise_for_status()
    return respuesta.json().get('access_token')


def sincronizar_boleta_background(ruta_archivo, nombre_proyecto, nombre_archivo):
    """Sube el archivo a SharePoint en segundo plano."""
    try:
        if not os.path.exists(ruta_archivo):
            logger.warning(f"[SHAREPOINT] Archivo no existe: {ruta_archivo}")
            return

        token = obtener_token()
        headers = {'Authorization': f'Bearer {token}'}

        url_drive = f"https://graph.microsoft.com/v1.0/sites/{settings.MS_SITE_ID}/drive"
        res_drive = requests.get(url_drive, headers=headers, timeout=15)
        res_drive.raise_for_status()
        drive_id = res_drive.json().get('id')

        nombre_carpeta_seguro = nombre_proyecto.replace("/", "-").replace("\\", "-").strip()

        url_subida = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/ObraGastos_Backups/{nombre_carpeta_seguro}/{nombre_archivo}:/content"
        )

        with open(ruta_archivo, 'rb') as archivo:
            datos_archivo = archivo.read()

        headers_subida = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/octet-stream'
        }
        res_subida = requests.put(
            url_subida, headers=headers_subida, data=datos_archivo, timeout=60
        )
        res_subida.raise_for_status()

        logger.info(f"[SHAREPOINT] Respaldado: {nombre_proyecto}/{nombre_archivo}")

    except requests.Timeout:
        logger.warning("[SHAREPOINT] Timeout en la conexión")
    except requests.HTTPError as e:
        logger.warning(f"[SHAREPOINT] Error HTTP: {e}")
    except Exception as e:
        logger.exception(f"[SHAREPOINT] Error inesperado: {e}")


def respaldar_en_sharepoint(gasto):
    """Lanza el respaldo en un hilo separado para no bloquear la respuesta."""
    if not _config_valida():
        logger.debug("[SHAREPOINT] Saltando respaldo: configuración ausente")
        return

    if not gasto.imagen or not hasattr(gasto.imagen, 'path'):
        logger.debug(f"[SHAREPOINT] Gasto #{gasto.id} sin archivo, saltando")
        return

    if not gasto.obra:
        logger.debug(f"[SHAREPOINT] Gasto #{gasto.id} sin obra, saltando")
        return

    ruta_absoluta = gasto.imagen.path
    nombre_proyecto = gasto.obra.nombre
    extension = os.path.splitext(ruta_absoluta)[1]
    nombre_archivo = f"Doc_{gasto.folio or 'SF'}_{gasto.rut_emisor or 'SinRut'}{extension}"

    logger.info(f"[SHAREPOINT] Respaldando '{nombre_archivo}' en '{nombre_proyecto}'")

    hilo = threading.Thread(
        target=sincronizar_boleta_background,
        args=(ruta_absoluta, nombre_proyecto, nombre_archivo),
        daemon=True
    )
    hilo.start()
