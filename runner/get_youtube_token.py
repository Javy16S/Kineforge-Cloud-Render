#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - YouTube Token Generator
Genera un nuevo YT_REFRESH_TOKEN permanente para GitHub Actions.
"""

import sys
import os

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("❌ Falta la librería google-auth-oauthlib. Instálala con:")
    print("   pip install google-auth-oauthlib")
    sys.exit(1)

# Permisos para subir y programar vídeos en YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("=" * 65)
    print("   🔑 KineForge - Generador de YouTube Refresh Token")
    print("=" * 65)
    print("Este asistente generará un nuevo YT_REFRESH_TOKEN para tu canal.\n")
    
    client_id = input("Introduce tu YT_CLIENT_ID: ").strip()
    client_secret = input("Introduce tu YT_CLIENT_SECRET: ").strip()

    if not client_id or not client_secret:
        print("❌ Error: Debes ingresar el Client ID y el Client Secret.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    print("\n🌐 Abriendo el navegador para autorizar la cuenta de YouTube...")
    print("👉 Si Google muestra 'Google no ha verificado esta aplicación', pulsa en:")
    print("   'Configuración avanzada' -> 'Ir a KineForge (no seguro)' y pulsa 'Continuar'.")
    
    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        # prompt='consent' y access_type='offline' FUERZAN a Google a entregar un refresh_token duradero
        creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")
    except Exception as e:
        print(f"\n❌ Error durante el inicio de sesión: {e}")
        sys.exit(1)

    print("\n" + "=" * 65)
    print("🎉 ¡AUTORIZACIÓN COMPLETADA CON ÉXITO!")
    print("=" * 65)
    print("\nTu nuevo YT_REFRESH_TOKEN es:\n")
    print(creds.refresh_token)
    print("\n" + "=" * 65)
    print("👉 Siguientes pasos:")
    print("1. Copia el token de arriba.")
    print("2. Ve a tu repositorio en GitHub:")
    print("   Settings -> Environments -> Zorojin (o Actions Secrets)")
    print("3. Edita 'YT_REFRESH_TOKEN' y pega este nuevo valor.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
