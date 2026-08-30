#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - YouTube Auto-Uploader
Sube videos generados a YouTube utilizando YouTube Data API v3 con subida resumable por chunks.
"""

import os
import sys
import json
import argparse
import time
import http.client
import httplib2

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# Reintentos para errores transitorios de red
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    http.client.NotConnected,
    http.client.IncompleteRead,
    http.client.ImproperConnectionState,
    http.client.CannotSendRequest,
    http.client.CannotSendHeader,
    http.client.ResponseNotReady,
    http.client.BadStatusLine,
)

def parse_args():
    parser = argparse.ArgumentParser(description="KineForge YouTube Uploader")
    parser.add_argument("--video", required=True, help="Ruta al archivo MP4 a subir")
    parser.add_argument("--metadata", required=True, help="Ruta al archivo metadata.json")
    return parser.parse_args()

def get_authenticated_service():
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Faltan variables de entorno requeridas: YT_CLIENT_ID, YT_CLIENT_SECRET o YT_REFRESH_TOKEN"
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    return build("youtube", "v3", credentials=creds)

def upload_video_resumable(youtube, video_path: str, metadata: dict):
    title = metadata.get("title", os.path.splitext(os.path.basename(video_path))[0])
    description = metadata.get("description", "Subido automáticamente vía KineForge Cloud Pipeline")
    tags = metadata.get("tags", ["KineForge", "Anime", "Dr Luffycs"])
    category_id = str(metadata.get("categoryId", "1")) # 1 = Film & Animation, 24 = Entertainment
    privacy_status = metadata.get("privacyStatus", "unlisted") # 'private', 'unlisted', 'public'

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": metadata.get("madeForKids", False),
        }
    }

    print(f"\n📤 Preparando subida a YouTube:")
    print(f"   Título:     {body['snippet']['title']}")
    print(f"   Privacidad: {privacy_status}")
    print(f"   Categoría:  {category_id}")
    print(f"   Archivo:    {video_path} ({os.path.getsize(video_path) / (1024*1024):.2f} MB)")

    # Chunks de 10 MB para estabilidad
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        chunksize=10 * 1024 * 1024,
        resumable=True
    )

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    retry = 0
    max_retries = 10

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                print(f"   Progreso de subida: {percent}%...")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                retry += 1
                if retry > max_retries:
                    raise Exception(f"Máximo número de reintentos alcanzado por error HTTP {e.resp.status}")
                sleep_seconds = retry * 5
                print(f"⚠️ Error recuperable {e.resp.status}. Reintentando en {sleep_seconds}s...")
                time.sleep(sleep_seconds)
            else:
                if "quotaExceeded" in str(e):
                    print("❌ ERROR CRÍTICO: La cuota diaria de la API de YouTube se ha agotado.")
                raise e
        except RETRIABLE_EXCEPTIONS as e:
            retry += 1
            if retry > max_retries:
                raise Exception(f"Máximo número de reintentos alcanzado por error de red: {e}")
            sleep_seconds = retry * 5
            print(f"⚠️ Error de red ({e}). Reintentando en {sleep_seconds}s...")
            time.sleep(sleep_seconds)

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f"\n🎉 ¡VÍDEO SUBIDO CON ÉXITO!")
    print(f"   ID:  {video_id}")
    print(f"   URL: {video_url}")

    # Subir miniatura personalizada si existe
    thumb_path = metadata.get("thumbnail")
    if thumb_path and os.path.exists(thumb_path):
        print(f"🖼️ Subiendo miniatura personalizada: {thumb_path}...")
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb_path)
            ).execute()
            print("✅ Miniatura subida con éxito.")
        except Exception as e:
            print(f"⚠️ No se pudo subir la miniatura: {e}")

    return video_id

def main():
    args = parse_args()

    if not os.path.exists(args.video):
        print(f"❌ Error: El archivo de video no existe: {args.video}")
        sys.exit(1)

    if not os.path.exists(args.metadata):
        print(f"❌ Error: El archivo metadata.json no existe: {args.metadata}")
        sys.exit(1)

    with open(args.metadata, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    try:
        youtube = get_authenticated_service()
        upload_video_resumable(youtube, args.video, metadata)
    except Exception as e:
        print(f"❌ Error al subir a YouTube: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
