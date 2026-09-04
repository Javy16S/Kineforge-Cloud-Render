#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Autonomous End-to-End Cloud Factory
Ejecuta la producción 100% autónoma en la nube (Zero-PC):
1. Descarga guion de Google Sheets
2. Genera TTS con Edge-TTS (con voces de personajes)
3. Monta timeline dinámico (cortes de 4s, Ken Burns KineForge y música)
4. Renderiza MP4 con FFmpeg
5. Sube a YouTube con subtítulos y miniatura
"""

import os
import sys
import json
import re
import csv
import io
import time
import shutil
import asyncio
import argparse
import subprocess
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from render import render_project
from upload_youtube import get_authenticated_service, upload_video_resumable

SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/14G4pyQLz6jGe8AW1yyU8KV4JHy1LmpF78-w1Riq3i2E/export?format=csv"

VOICE_MAP = {
    "Narrador": {"voice": "es-ES-AlvaroNeural", "rate": "-2%", "pitch": "-6Hz"},
    "Goku": {"voice": "es-MX-JorgeNeural", "rate": "+2%", "pitch": "-1Hz"},
    "Vegeta": {"voice": "es-MX-JorgeNeural", "rate": "-1%", "pitch": "-7Hz"},
    "Dende": {"voice": "es-ES-AlvaroNeural", "rate": "+4%", "pitch": "+6Hz"},
    "Mister Popo": {"voice": "es-ES-AlvaroNeural", "rate": "-6%", "pitch": "-10Hz"}
}

KEN_BURNS_PRESETS = [
    {"start": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "end": {"x": 0.04, "y": 0.04, "w": 0.92, "h": 0.92}},
    {"start": {"x": 0.04, "y": 0.04, "w": 0.92, "h": 0.92}, "end": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
    {"start": {"x": 0.06, "y": 0.02, "w": 0.94, "h": 0.94}, "end": {"x": 0.0, "y": 0.02, "w": 0.94, "h": 0.94}},
    {"start": {"x": 0.0, "y": 0.02, "w": 0.94, "h": 0.94}, "end": {"x": 0.06, "y": 0.02, "w": 0.94, "h": 0.94}},
    {"start": {"x": 0.02, "y": 0.02, "w": 0.96, "h": 0.96}, "end": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.90}}
]

def parse_args():
    parser = argparse.ArgumentParser(description="KineForge Autonomous Cloud Factory")
    parser.add_argument("--history-index", type=int, default=0, help="Índice de la historia en Google Sheets (0 = primera)")
    parser.add_argument("--chapter-num", type=int, default=1, help="Número de capítulo a producir (1..5)")
    parser.add_argument("--work-dir", default="/tmp/kineforge_factory", help="Directorio temporal de trabajo")
    parser.add_argument("--output-video", default="/tmp/final_video.mp4", help="Ruta del video final")
    parser.add_argument("--dry-run", action="store_true", help="Simular subida a YouTube sin consumir cuota")
    return parser.parse_args()

def split_text_into_dynamic_cuts(text, target_words=10):
    clauses = [c.strip() for c in re.split(r'[,;.!?]+\s*', text) if c.strip()]
    segments = []
    curr = []
    for c in clauses:
        curr.append(c)
        count = sum(len(x.split()) for x in curr)
        if count >= target_words:
            segments.append(', '.join(curr) + '.')
            curr = []
    if curr:
        if segments and sum(len(x.split()) for x in curr) < 5:
            segments[-1] = segments[-1][:-1] + ', ' + ', '.join(curr) + '.'
        else:
            segments.append(', '.join(curr) + '.')
    return segments

def parse_script_with_dynamic_pacing(guion_text):
    paragraphs = [p.strip() for p in guion_text.split("\n") if p.strip()]
    atomic_cuts = []
    for p in paragraphs:
        if p.startswith("—") or p.startswith("-"):
            p_clean = p.lstrip("—- ").strip()
            p_low = p_clean.lower()
            if "dende" in p_low:
                char = "Dende"
            elif "popo" in p_low:
                char = "Mister Popo"
            elif "vegeta" in p_low:
                char = "Vegeta"
            elif "goku" in p_low or any(k in p_low for k in ["¡", "¿", "kamehameha", "maldición", "milk", "cena"]):
                char = "Goku"
            else:
                char = "Narrador"
            sub_cuts = split_text_into_dynamic_cuts(p_clean, target_words=10)
            for s in sub_cuts:
                atomic_cuts.append({"character": char, "text": s, "is_dialogue": True})
        else:
            sub_cuts = split_text_into_dynamic_cuts(p, target_words=10)
            for s in sub_cuts:
                atomic_cuts.append({"character": "Narrador", "text": s, "is_dialogue": False})
    return atomic_cuts

def get_audio_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except:
        return 0.0

async def main():
    args = parse_args()
    print("==================================================")
    print("🌟 KINEFORGE AUTONOMOUS CLOUD FACTORY v1.0")
    print(f"Capítulo: {args.chapter_num} | WorkDir: {args.work_dir}")
    print("==================================================")

    os.makedirs(args.work_dir, exist_ok=True)
    assets_dir = os.path.join(args.work_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    tts_dir = os.path.join(args.work_dir, "tts")
    os.makedirs(tts_dir, exist_ok=True)

    # 1. Descargar Google Sheets
    print("\n📥 Descargando guion en vivo desde Google Sheets...")
    req = urllib.request.Request(SHEETS_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    csv_content = urllib.request.urlopen(req).read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    if args.history_index >= len(rows):
        raise IndexError(f"Índice de historia {args.history_index} fuera de rango (total {len(rows)})")

    story_row = rows[args.history_index]
    sheet_title = story_row.get('TÍTULO DEL VIDEO', 'Goku Encerrado Mil Años')
    
    chapter_arg = str(args.chapter_num).strip().lower()
    if chapter_arg in ["full", "completo", "0", "pelicula"]:
        is_full_movie = True
        cap_parts = []
        for c_idx in range(1, 6):
            p_txt = story_row.get(f'CAPÍTULO {c_idx}', '').strip()
            if p_txt:
                cap_parts.append(p_txt)
        cap_text = "\n\n".join(cap_parts)
        display_title = f"{sheet_title} | PELÍCULA COMPLETA (Capítulos 1 al 5)"
    else:
        is_full_movie = False
        cap_text = story_row.get(f'CAPÍTULO {args.chapter_num}', '').strip()
        display_title = f"{sheet_title} | Capítulo {args.chapter_num}"

    if not cap_text:
        raise ValueError(f"No se encontró texto para el CAPÍTULO {args.chapter_num} en la fila seleccionada.")

    print(f"📖 Título: {display_title}")
    print(f"   Palabras: {len(cap_text.split()):,} | Caracteres: {len(cap_text):,}")

    # 2. Parsear en cortes dinámicos (3-5 segundos)
    atomic_cuts = parse_script_with_dynamic_pacing(cap_text)
    print(f"✂️ Cortes atómicos generados: {len(atomic_cuts)} frases individuales")

    # 3. Generar TTS para cada corte con Edge-TTS
    print("\n🎙️ Generando locuciones en la nube con Edge-TTS...")
    import edge_tts
    sem = asyncio.Semaphore(5)

    async def gen_cut(idx, cut):
        async with sem:
            char = cut["character"]
            text = cut["text"]
            cfg = VOICE_MAP.get(char, VOICE_MAP["Narrador"])
            out_file = os.path.join(tts_dir, f"cut_{idx:04d}_{char}.mp3")
            if not os.path.exists(out_file) or os.path.getsize(out_file) < 200:
                comm = edge_tts.Communicate(text, cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
                await comm.save(out_file)
            dur = get_audio_duration(out_file)
            return {"idx": idx, "character": char, "text": text, "file": out_file, "duration": dur}

    tasks = [gen_cut(i, c) for i, c in enumerate(atomic_cuts)]
    audio_segments = await asyncio.gather(*tasks)
    audio_segments = sorted(audio_segments, key=lambda x: x["idx"])
    print(f"✅ {len(audio_segments)} audios generados.")

    # 4. Master Audio con 4.0s de intro Zorojin
    silence_4s = os.path.join(tts_dir, "silence_4s.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "4.0", silence_4s], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    concat_audio_txt = os.path.join(tts_dir, "concat_audio.txt")
    with open(concat_audio_txt, "w", encoding="utf-8") as af_txt:
        af_txt.write(f"file '{silence_4s}'\n")
        for item in audio_segments:
            af_txt.write(f"file '{item['file']}'\n")

    master_audio = os.path.join(assets_dir, "audio_master.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_audio_txt, "-c", "copy", master_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total_duration = get_audio_duration(master_audio)
    print(f"🎧 Master Audio compilado: {total_duration:.2f}s (~{total_duration/60:.1f} min)")

    # 5. Música de fondo con 4s de silencio inicial
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assets_lib = os.path.join(repo_root, "assets_library")
    music_lib = os.path.join(assets_lib, "music")
    music_files = sorted([os.path.join(music_lib, f) for f in os.listdir(music_lib) if f.lower().endswith(('.mp3', '.wav'))])

    music_4s_silence = os.path.join(tts_dir, "music_silence_4s.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "4.0", music_4s_silence], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    music_concat_txt = os.path.join(tts_dir, "music_concat.txt")
    with open(music_concat_txt, "w", encoding="utf-8") as mf_txt:
        mf_txt.write(f"file '{music_4s_silence}'\n")
        for m in music_files:
            mf_txt.write(f"file '{m}'\n")

    dest_music_bg = os.path.join(assets_dir, "music_bg.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", music_concat_txt, "-t", str(total_duration), "-c:a", "libmp3lame", "-b:a", "192k", dest_music_bg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. Motor de Memoria de Sujeto (Stateful Director Engine)
    class StatefulDirector:
        def __init__(self, goku_lib, dbs_lib, scen_lib):
            self.goku_lib = goku_lib
            self.dbs_lib = dbs_lib
            self.scen_lib = scen_lib
            self.current_subject = "Escenario"
            self.subject_streak = 0
            self.goku_idx = 0
            self.dbs_idx = 0
            self.scen_idx = 0

        def select_image(self, cut_item, cut_index):
            char = cut_item.get("character", "Narrador")
            text = cut_item.get("text", "").lower()

            # 1. Diálogos directos de personajes
            if char == "Goku":
                self.current_subject = "Goku"
                self.subject_streak = 0
            elif char in ["Dende", "Mister Popo", "Popo"]:
                self.current_subject = "DBS"
                self.subject_streak = 0
            elif char == "Vegeta":
                self.current_subject = "Vegeta"
                self.subject_streak = 0
            else: # Narrador con análisis semántico e inercia de sujeto
                goku_explicit = ["goku", "saiyajin", "saiyan", "kamehameha", "kakarotto", "super saiyajin", "ssj", "ki dorado", "guerrero de la tierra", "entrenamiento"]
                dbs_explicit = ["dende", "popo", "mr. popo", "kami-sama", "kami sama", "namekiano", "dios de la tierra"]
                env_explicit = ["templo", "palacio", "habitación del tiempo", "puerta", "portal", "grieta", "terremoto", "temblor", "sismo", "cielo", "suelo", "atmósfera", "vacío", "horizonte", "escombros", "plano dimensional", "gravedad", "terreno", "derrumbe"]
                anaphora_triggers = ["sus ojos", "su mirada", "su cuerpo", "pensó", "recordó", "sintió", "dio un paso", "se levantó", "apretó", "en su mente", "su corazón", "respiró", "su poder", "sus puños", "su rostro", "decidió", "sabía que", "no podía creer", "cerró los ojos"]

                if any(w in text for w in goku_explicit):
                    self.current_subject = "Goku"
                    self.subject_streak = 0
                elif any(w in text for w in dbs_explicit):
                    self.current_subject = "DBS"
                    self.subject_streak = 0
                elif any(w in text for w in env_explicit):
                    self.current_subject = "Escenario"
                    self.subject_streak = 0
                elif any(w in text for w in anaphora_triggers):
                    # Mantener el sujeto activo por inercia dramática
                    self.subject_streak += 1
                else:
                    self.subject_streak += 1
                    # Corte de variedad para evitar fatiga visual
                    if self.subject_streak > 3:
                        self.current_subject = "Escenario" if self.current_subject != "Escenario" else "Goku"
                        self.subject_streak = 0

            # 2. Asignación de imagen sin repetir
            if self.current_subject == "Goku":
                img = self.goku_lib[self.goku_idx % len(self.goku_lib)]
                self.goku_idx += 1
            elif self.current_subject == "DBS":
                img = self.dbs_lib[self.dbs_idx % len(self.dbs_lib)] if self.dbs_lib else self.goku_lib[0]
                self.dbs_idx += 1
            else:
                img = self.scen_lib[self.scen_idx % len(self.scen_lib)]
                self.scen_idx += 1

            return img

    # Cargar bibliotecas de assets
    goku_lib = sorted([os.path.join(assets_lib, "goku", f) for f in os.listdir(os.path.join(assets_lib, "goku"))])
    dbs_lib = sorted([os.path.join(assets_lib, "dbs", f) for f in os.listdir(os.path.join(assets_lib, "dbs"))])
    scen_lib = sorted([os.path.join(assets_lib, "scenarios", f) for f in os.listdir(os.path.join(assets_lib, "scenarios"))])
    intro_img = os.path.join(assets_lib, "intro", "Zorojin_Intro.jpg")

    director = StatefulDirector(goku_lib, dbs_lib, scen_lib)

    manifest_clips = []
    shutil.copy2(intro_img, os.path.join(assets_dir, "img_0000.jpg"))
    manifest_clips.append({
        "id": "intro_zorojin_4s",
        "asset": "img_0000.jpg",
        "audioIn": 0.0,
        "audioOut": 4.0,
        "zoom": {"start": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "end": {"x": 0.015, "y": 0.015, "w": 0.97, "h": 0.97}}
    })

    current_t = 4.0
    asset_map = {}
    asset_counter = 1

    for idx, seg in enumerate(audio_segments):
        start_t = current_t
        end_t = current_t + seg["duration"]
        current_t = end_t
        orig_img = director.select_image(seg, idx)
        if orig_img not in asset_map:
            ext = os.path.splitext(orig_img)[1]
            img_name = f"img_{asset_counter:04d}{ext}"
            asset_counter += 1
            shutil.copy2(orig_img, os.path.join(assets_dir, img_name))
            asset_map[orig_img] = img_name
        else:
            img_name = asset_map[orig_img]

        manifest_clips.append({
            "id": f"clip_{idx:04d}",
            "asset": img_name,
            "audioIn": round(start_t, 3),
            "audioOut": round(end_t, 3),
            "zoom": KEN_BURNS_PRESETS[idx % len(KEN_BURNS_PRESETS)]
        })

    # Subtítulos SRT
    srt_path = os.path.join(assets_dir, "subtitles.srt")
    def format_srt_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(srt_path, "w", encoding="utf-8") as srt_f:
        for idx, clip in enumerate(manifest_clips[1:]):
            srt_f.write(f"{idx+1}\n")
            srt_f.write(f"{format_srt_time(clip['audioIn'])} --> {format_srt_time(clip['audioOut'])}\n")
            srt_f.write(f"{audio_segments[idx]['text']}\n\n")

    manifest = {
        "version": "1.0",
        "aspectRatio": "16:9",
        "duration": total_duration,
        "fps": 30,
        "audioFile": "audio_master.mp3",
        "musicFile": "music_bg.mp3",
        "musicVolume": 0.12,
        "clips": manifest_clips
    }
    manifest_file = os.path.join(args.work_dir, "manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    metadata = {
        "title": display_title,
        "description": f"{display_title} producido y renderizado en la nube.\n\n#DragonBall #Goku #AnimeFanfic #Zorojin",
        "tags": ["Dragon Ball", "Goku", "Zorojin", "Habitacion del Tiempo", "Anime Fanfic", "Super Saiyajin", "Pelicula Completa"],
        "categoryId": "1",
        "privacyStatus": "unlisted",
        "madeForKids": False,
        "dryRun": args.dry_run,
        "subtitles": srt_path
    }
    metadata_file = os.path.join(args.work_dir, "metadata.json")
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 7. Renderizar Video con FFmpeg
    print(f"\n🎬 Renderizando vídeo MP4 final con motor v3.0 ({len(manifest_clips)} clips)...")
    render_project(manifest_file, assets_dir, args.output_video, ffmpeg_bin="ffmpeg")

    # 8. Subir a YouTube
    print("\n🚀 Subiendo a YouTube con subtítulos sincronizados...")
    if args.dry_run:
        print("ℹ️ Modo Dry-Run activo: No se subirá a YouTube.")
    else:
        youtube = get_authenticated_service()
        upload_video_resumable(youtube, args.output_video, metadata)

    print("\n🎉 ¡PRODUCCIÓN 100% COMPLETADA CON ÉXITO EN LA NUBE!")

if __name__ == "__main__":
    asyncio.run(main())
