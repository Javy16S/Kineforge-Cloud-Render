#!/usr/bin/env python3
"""
KineForge Cloud Pipeline - Headless FFmpeg Renderer
Renderiza proyectos KineForge a video MP4 (H.264 / AAC) en entornos Linux/GitHub Actions.
"""

import os
import sys
import json
import argparse
import subprocess
import time
from typing import Dict, Any, List

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

RESOLUTION_MAP = {
    '16:9': {'width': 1920, 'height': 1080},
    '9:16': {'width': 1080, 'height': 1920},
}

def parse_args():
    parser = argparse.ArgumentParser(description="KineForge Cloud FFmpeg Renderer")
    parser.add_argument("--manifest", required=True, help="Ruta al archivo manifest.json del proyecto")
    parser.add_argument("--assets", required=True, help="Ruta al directorio de assets")
    parser.add_argument("--output", required=True, help="Ruta del archivo MP4 de salida")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="Binario de FFmpeg a usar")
    return parser.parse_args()

def build_zoompan_filter(clip: Dict[str, Any], width: int, height: int, fps: int = 30) -> str:
    """
    Construye la expresión zoompan de FFmpeg para interpolar el zoom Ken Burns
    entre el área inicial (start) y el área final (end).
    """
    dur_frames = max(1, int(float(clip.get("duration", 5.0)) * fps))
    zoom = clip.get("zoom", {})
    start = zoom.get("start", {"x": 0, "y": 0, "w": 1, "h": 1})
    end = zoom.get("end", {"x": 0, "y": 0, "w": 1, "h": 1})

    # Zoom scale: relación inversa del ancho del rectángulo de recorte
    # Si w=1.0 -> z=1.0. Si w=0.5 -> z=2.0
    start_z = 1.0 / max(0.01, float(start.get("w", 1.0)))
    end_z = 1.0 / max(0.01, float(end.get("w", 1.0)))

    # Posición X y Y
    start_x = float(start.get("x", 0.0))
    end_x = float(end.get("x", 0.0))
    start_y = float(start.get("y", 0.0))
    end_y = float(end.get("y", 0.0))

    # Expresión de interpolación lineal sobre 'on' (frame actual de 0 a dur_frames-1)
    # z: start_z + (end_z - start_z) * (on / (dur_frames - 1))
    if dur_frames > 1 and abs(end_z - start_z) > 0.001:
        z_expr = f"{start_z:.4f}+({end_z - start_z:.4f})*(on/{dur_frames - 1})"
    else:
        z_expr = f"{start_z:.4f}"

    # x: (start_x + (end_x - start_x) * (on / dur_frames)) * (iw - iw/zoom)
    if dur_frames > 1 and abs(end_x - start_x) > 0.001:
        x_norm_expr = f"({start_x:.4f}+({end_x - start_x:.4f})*(on/{dur_frames - 1}))"
    else:
        x_norm_expr = f"{start_x:.4f}"

    if dur_frames > 1 and abs(end_y - start_y) > 0.001:
        y_norm_expr = f"({start_y:.4f}+({end_y - start_y:.4f})*(on/{dur_frames - 1}))"
    else:
        y_norm_expr = f"{start_y:.4f}"

    x_expr = f"{x_norm_expr}*(iw-iw/zoom)"
    y_expr = f"{y_norm_expr}*(ih-ih/zoom)"

    return f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={dur_frames}:s={width}x{height}:fps={fps}"

def render_project(manifest_path: str, assets_dir: str, output_path: str, ffmpeg_bin: str = "ffmpeg"):
    start_time = time.time()
    print(f"==================================================")
    print(f"🚀 KineForge Cloud Renderer v1.0")
    print(f"Manifest: {manifest_path}")
    print(f"Assets:   {assets_dir}")
    print(f"Output:   {output_path}")
    print(f"==================================================")

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"No se encontró el manifest en {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    aspect_ratio = manifest.get("aspectRatio", "16:9")
    res = RESOLUTION_MAP.get(aspect_ratio, RESOLUTION_MAP["16:9"])
    width = res["width"]
    height = res["height"]
    fps = manifest.get("fps", 30)

    clips = manifest.get("clips", [])
    audio_path = manifest.get("audioFile")
    music_path = manifest.get("musicFile")
    subtitle_file = manifest.get("subtitleFile")

    total_duration = manifest.get("duration", 0.0)
    if total_duration <= 0 and clips:
        total_duration = max(float(c.get("audioOut", c.get("timeEnd", 0))) for c in clips)

    print(f"📊 Duración total: {total_duration:.2f}s | Resolución: {width}x{height} ({aspect_ratio}) @ {fps}fps")

    input_args = ["-y", "-threads", "0"]
    filter_complex_lines = []

    # Input 0: Fondo base negro
    input_args.extend([
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={fps}:d={total_duration:.3f}"
    ])
    current_layer = "[0:v]"

    # Mapeo de inputs adicionales
    input_index = 1
    visual_inputs = []

    for idx, clip in enumerate(clips):
        filename = clip.get("asset") or clip.get("resource")
        if not filename:
            continue
            
        full_asset_path = os.path.join(assets_dir, os.path.basename(filename))
        if not os.path.exists(full_asset_path):
            print(f"⚠️ Aviso: Asset no encontrado: {full_asset_path}. Omitiendo clip {idx}.")
            continue

        clip_start = float(clip.get("audioIn", clip.get("timeStart", 0.0)))
        clip_end = float(clip.get("audioOut", clip.get("timeEnd", clip_start + 5.0)))
        clip_dur = max(0.1, clip_end - clip_start)

        input_args.extend(["-loop", "1", "-t", f"{clip_dur:.3f}", "-i", full_asset_path])
        
        # Filtro de zoom Ken Burns
        clip_data = {"duration": clip_dur, "zoom": clip.get("zoom", {})}
        zoom_filter = build_zoompan_filter(clip_data, width, height, fps)
        
        filter_complex_lines.append(f"[{input_index}:v]{zoom_filter}[v_clip_{idx}];")

        # Overlay sobre el lienzo
        next_layer = f"[canvas_{idx}]"
        filter_complex_lines.append(
            f"{current_layer}[v_clip_{idx}]overlay=x=0:y=0:enable='between(t,{clip_start:.3f},{clip_end:.3f})'{next_layer};"
        )
        current_layer = next_layer
        input_index += 1

    # Manejo de audio
    audio_inputs = []
    
    # Audio principal (diálogos / narración)
    has_main_audio = False
    if audio_path:
        full_audio_path = os.path.join(assets_dir, os.path.basename(audio_path))
        if os.path.exists(full_audio_path):
            input_args.extend(["-i", full_audio_path])
            audio_inputs.append(f"[{input_index}:a]")
            has_main_audio = True
            input_index += 1

    # Música de fondo (opcional)
    has_music = False
    if music_path:
        full_music_path = os.path.join(assets_dir, os.path.basename(music_path))
        if os.path.exists(full_music_path):
            music_vol = manifest.get("musicVolume", 0.15)
            input_args.extend(["-i", full_music_path])
            filter_complex_lines.append(f"[{input_index}:a]volume={music_vol:.2f}[a_music];")
            audio_inputs.append("[a_music]")
            has_music = True
            input_index += 1

    # Mezcla de audio
    if len(audio_inputs) > 1:
        mix_inputs = "".join(audio_inputs)
        filter_complex_lines.append(f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=2[a_out];")
        final_audio_tag = "[a_out]"
    elif len(audio_inputs) == 1:
        final_audio_tag = audio_inputs[0]
    else:
        # Generar silencio si no hay audio
        input_args.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo"])
        final_audio_tag = f"[{input_index}:a]"
        input_index += 1

    # Subtítulos (si existen)
    final_video_tag = current_layer
    if subtitle_file:
        full_sub_path = os.path.join(assets_dir, os.path.basename(subtitle_file))
        if os.path.exists(full_sub_path):
            # Escapar caracteres para FFmpeg en Linux
            sub_escaped = full_sub_path.replace(":", "\\:").replace("'", "\\'")
            filter_complex_lines.append(f"{current_layer}subtitles='{sub_escaped}'[v_sub_out];")
            final_video_tag = "[v_sub_out]"

    # Unir grafo de filtros
    filter_graph = "".join(filter_complex_lines)
    # Limpiar punto y coma final
    if filter_graph.endswith(";"):
        filter_graph = filter_graph[:-1]

    # Comando FFmpeg final
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    cmd = [ffmpeg_bin] + input_args
    if filter_graph:
        cmd.extend(["-filter_complex", filter_graph])
        cmd.extend(["-map", final_video_tag, "-map", final_audio_tag])
    
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{total_duration:.3f}",
        output_path
    ])

    print("\n🎬 Ejecutando render FFmpeg...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    elapsed = time.time() - start_time
    if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✅ Render completado con éxito en {elapsed:.1f}s")
        print(f"📦 Archivo generado: {output_path} ({file_size_mb:.2f} MB)")
        return True
    else:
        print(f"❌ Error durante el renderizado de FFmpeg (Código {res.returncode}):")
        print(res.stderr[-2000:] if res.stderr else "Error desconocido")
        sys.exit(1)

if __name__ == "__main__":
    args = parse_args()
    render_project(args.manifest, args.assets, args.output, args.ffmpeg_bin)
