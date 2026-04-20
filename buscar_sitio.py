import os
import requests
from dotenv import load_dotenv

# 1. Cargamos el archivo .env donde están tus secretos reales
load_dotenv()

# 2. Leemos las llaves desde el sistema (NUNCA PEGAR TEXTO AQUÍ)
CLIENT_ID = os.getenv('MS_CLIENT_ID')
CLIENT_SECRET = os.getenv('MS_CLIENT_SECRET')
TENANT_ID = os.getenv('MS_TENANT_ID')

def buscar_mi_sitio():
    # Verificación de seguridad: si no hay llaves, detenemos el proceso
    if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
        print("❌ Error: No se encontraron las llaves en el archivo .env")
        print("Asegúrate de tener un archivo .env con MS_CLIENT_ID, MS_CLIENT_SECRET y MS_TENANT_ID")
        return

    print("1. Obteniendo pase de entrada a Microsoft...")
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials',
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        token = response.json().get('access_token')
        print("✅ ¡Conexión exitosa!\n")
        
        # --- BUSCAR EL SITIO ---
        palabra_clave = "Ingenieria y Construccion VC Limitada" 
        print(f"2. Buscando sitios que contengan: '{palabra_clave}'...")
        
        headers = {'Authorization': f'Bearer {token}'}
        url_sites = f"https://graph.microsoft.com/v1.0/sites?search={palabra_clave}"
        
        res_sites = requests.get(url_sites, headers=headers)
        res_sites.raise_for_status()
        
        sitios = res_sites.json().get('value', [])
        
        if not sitios:
            print(f"⚠️ No se encontraron sitios con la palabra: {palabra_clave}")
            return

        print(f"✨ Se encontraron {len(sitios)} sitios:")
        for sitio in sitios:
            print("-" * 60)
            print(f"📁 Nombre: {sitio.get('displayName')}")
            print(f"🔗 URL: {sitio.get('webUrl')}")
            print(f"🔑 SITE_ID: '{sitio.get('id')}'")
            print("-" * 60)
            print("\n💡 COPIA EL SITE_ID de arriba y pégalo en tu archivo .env como MS_SITE_ID\n")

    except requests.exceptions.HTTPError as err:
        print("❌ Error de Microsoft Graph:")
        print(err.response.json())
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")

if __name__ == '__main__':
    buscar_mi_sitio()