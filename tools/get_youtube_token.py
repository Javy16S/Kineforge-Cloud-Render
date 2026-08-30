#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Generador de Tokens OAuth para YouTube
Ejecuta este script en tu ordenador para autorizar un canal de YouTube y obtener su Refresh Token.
"""

import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("=" * 60)
    print("🔑 KineForge - Generador de Refresh Token para YouTube")
    print("=" * 60)
    print("Para obtener las credenciales de un canal:")
    print("1. Ve a Google Cloud Console (https://console.cloud.google.com/)")
    print("2. Crea/Selecciona el proyecto del canal y habilita 'YouTube Data API v3'.")
    print("3. Crea credenciales OAuth 2.0 de tipo 'Aplicación de escritorio'.")
    print("-" * 60)

    client_id = input("Introduce el CLIENT ID: ").strip()
    client_secret = input("Introduce el CLIENT SECRET: ").strip()

    if not client_id or not client_secret:
        print("❌ Error: Client ID y Client Secret son obligatorios.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"]
        }
    }

    print("\n🌐 Abriendo el navegador para autorizar la cuenta de YouTube...")
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(
        port=8080,
        access_type="offline",
        prompt="consent",
        success_message="¡Autorización completada con éxito! Puedes cerrar esta ventana."
    )

    if not creds.refresh_token:
        print("\n⚠️ AVISO: Google no devolvió un refresh_token nuevo.")
        print("Si ya habías autorizado la app antes, ve a tus permisos de cuenta de Google y revócalos para generar un token limpio.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("🎉 ¡CREDENCIALES GENERADAS CON ÉXITO!")
    print("Copia y pega estos 3 valores en los Secrets de tu GitHub Environment:")
    print("=" * 60)
    print(f"\n[1] Nombre del Secret: YT_CLIENT_ID")
    print(f"    Valor: {client_id}")
    print(f"\n[2] Nombre del Secret: YT_CLIENT_SECRET")
    print(f"    Valor: {client_secret}")
    print(f"\n[3] Nombre del Secret: YT_REFRESH_TOKEN")
    print(f"    Valor: {creds.refresh_token}")
    print("=" * 60)

if __name__ == "__main__":
    main()
