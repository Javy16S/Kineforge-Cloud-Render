"""
Dataset Registry & Dynamic Asset Catalog for KineForge (Local + Cloud)
======================================================================
Proporciona indexación dinámica, resolución semántica de emociones con grafo de fallback,
y exportación de contexto para el nodo de IA (LLM / Script Director).
"""

import os
import sys
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Rutas estándar de búsqueda
DEFAULT_SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets_library"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_library"),
    r"E:\Dataset_Dragon_Ball\Ordered Images",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Ordered Images"),
    r"D:\Descargas\Javier\Elementos"
]

# Grafo Semántico de Fallback para Emociones y Acciones
SEMANTIC_EMOTION_FALLBACKS = {
    "Combate": ["Enfadado", "Neutral"],
    "Herido": ["Triste", "Enfadado", "Neutral"],
    "Sorprendido": ["Neutral", "Enfadado"],
    "Comico": ["Alegre", "Neutral"],
    "Confiado": ["Alegre", "Neutral"],
    "Avergonzado": ["Comico", "Alegre", "Neutral"],
    "Preocupado": ["Triste", "Neutral"],
    "Confundido": ["Sorprendido", "Neutral"],
    "Entrenamiento": ["Combate", "Neutral"],
    "Genkidama": ["Combate", "Enfadado", "Neutral"],
    "Fin_Z": ["Alegre", "Neutral"],
    "Triste": ["Neutral"],
    "Enfadado": ["Neutral"],
    "Alegre": ["Neutral"],
    "Neutral": []
}

# Alias canónicos de Personajes
CHARACTER_ALIASES = {
    "bills": "Bills_Beerus",
    "beerus": "Bills_Beerus",
    "billsbeerus": "Bills_Beerus",
    "roshi": "Muten_Roshi",
    "mutenroshi": "Muten_Roshi",
    "maestroroshi": "Muten_Roshi",
    "buu": "Majin_Buu",
    "majinbuu": "Majin_Buu",
    "mrbuu": "Majin_Buu",
    "ginyu": "Capitan_Ginyu",
    "capitanginyu": "Capitan_Ginyu",
    "satan": "Mr_Satan",
    "mrsatan": "Mr_Satan",
    "milk": "Milk_ChiChi",
    "chichi": "Milk_ChiChi",
    "milkchichi": "Milk_ChiChi",
    "trunksfuturo": "Trunks_del_Futuro",
    "trunksdelfuturo": "Trunks_del_Futuro",
    "trunks_nino": "Trunks_Niño",
    "trunksnino": "Trunks_Niño",
    "a17": "Androide_17",
    "n17": "Androide_17",
    "numero17": "Androide_17",
    "androide17": "Androide_17",
    "a18": "Androide_18",
    "n18": "Androide_18",
    "numero18": "Androide_18",
    "androide18": "Androide_18",
    "frieza": "Freezer",
    "vegetta": "Vegeta",
    "kakarotto": "Goku",
    "kakaroto": "Goku",
}

# Alias canónicos de Fases / Transformaciones
PHASE_ALIASES = {
    "base": "Base",
    "normal": "Base",
    "ssj": "SSJ1",
    "ssj1": "SSJ1",
    "supersaiyan": "SSJ1",
    "supersaiyajin": "SSJ1",
    "ssj2": "SSJ2",
    "ssj3": "SSJ3",
    "god": "SSJGOD",
    "ssjgod": "SSJGOD",
    "dios": "SSJGOD",
    "ssjdios": "SSJGOD",
    "blue": "SSJBLUE",
    "ssjblue": "SSJBLUE",
    "ultrainstinto": "ULTRAINSTINTO",
    "ui": "ULTRAINSTINTO",
    "migattenogokui": "ULTRAINSTINTO",
    "kaioken": "Kaioken",
    "kid": "Kid"
}

# Alias canónicos de Emociones
EMOTION_ALIASES = {
    "alegre": "Alegre",
    "feliz": "Alegre",
    "contento": "Alegre",
    "sonriendo": "Alegre",
    "riendo": "Alegre",
    "enfadado": "Enfadado",
    "enojado": "Enfadado",
    "furioso": "Enfadado",
    "furia": "Enfadado",
    "triste": "Triste",
    "llorando": "Triste",
    "derrotado": "Triste",
    "neutral": "Neutral",
    "serio": "Neutral",
    "calmado": "Neutral",
    "normal": "Neutral",
    "combate": "Combate",
    "pelea": "Combate",
    "lucha": "Combate",
    "ataque": "Combate",
    "herido": "Herido",
    "dañado": "Herido",
    "lesionado": "Herido",
    "sorprendido": "Sorprendido",
    "impactado": "Sorprendido",
    "asombrado": "Sorprendido",
    "shock": "Sorprendido",
    "comico": "Comico",
    "divertido": "Comico",
    "chistoso": "Comico",
    "confiado": "Confiado",
    "arrogante": "Confiado",
    "orgulloso": "Confiado"
}


def clean_string(text: Any) -> str:
    """Normaliza texto eliminando acentos, caracteres especiales y mayúsculas."""
    if not text:
        return ""
    t = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'[^a-z0-9]', '', t.lower())


class DatasetRegistry:
    """Registro maestro e indexador del dataset de imágenes de KineForge."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = self._locate_root_dir(root_dir)
        self.chars_dir = os.path.join(self.root_dir, "Characters") if self.root_dir else None
        self.scens_dir = os.path.join(self.root_dir, "Scenarios") if self.root_dir else None
        
        self.catalog_path = self._determine_catalog_path()
        self.catalog: Dict[str, Any] = {}
        self.pools: Dict[str, Dict[str, Any]] = {}

        self.load_or_build_catalog()

    def _locate_root_dir(self, explicit_root: Optional[str] = None) -> str:
        candidates = []
        if explicit_root:
            candidates.append(explicit_root)
        candidates.extend(DEFAULT_SEARCH_PATHS)

        for p in candidates:
            if p and os.path.exists(p):
                # Validar si contiene Characters o Scenarios
                if os.path.exists(os.path.join(p, "Characters")) or os.path.exists(os.path.join(p, "characters")):
                    return p
                if os.path.exists(os.path.join(p, "Ordered Images", "Characters")):
                    return os.path.join(p, "Ordered Images")
        
        # Si ninguno existe, retornar el primer candidato por defecto
        return explicit_root or DEFAULT_SEARCH_PATHS[0]

    def _determine_catalog_path(self) -> str:
        same_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_catalog.json")
        if os.path.exists(same_dir):
            return same_dir
        if self.root_dir and os.path.exists(self.root_dir):
            return os.path.join(self.root_dir, "dataset_catalog.json")
        local_data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(local_data, exist_ok=True)
        return os.path.join(local_data, "dataset_catalog.json")

    def build_catalog(self) -> Dict[str, Any]:
        """Escanea el disco y genera la estructura completa del catálogo."""
        catalog = {
            "version": "2.0",
            "root_dir": self.root_dir,
            "characters": {},
            "scenarios": {},
            "stats": {
                "total_characters": 0,
                "total_images": 0
            }
        }

        if not self.chars_dir or not os.path.exists(self.chars_dir):
            return catalog

        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        total_imgs = 0

        # 1. Escanear Personajes
        for char_name in sorted(os.listdir(self.chars_dir)):
            char_path = os.path.join(self.chars_dir, char_name)
            if not os.path.isdir(char_path) or char_name.startswith("_") or char_name.startswith("."):
                continue

            char_entry: Dict[str, Any] = {
                "phases": {},
                "total_images": 0
            }

            # Explorar subdirectorios de fases y emociones
            # Caso A: Estructura Character/Phase/Emotion (ej. Goku/Base/Neutral)
            # Caso B: Estructura Character/Emotion plana (ej. Piccolo/Neutral)
            for item in sorted(os.listdir(char_path)):
                item_path = os.path.join(char_path, item)
                if not os.path.isdir(item_path) or item.startswith("_") or item.startswith("."):
                    continue

                # Determinar si item es una Fase o directamente una Emoción
                # Verificamos si dentro de item_path hay subcarpetas o imágenes
                sub_dirs = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d)) and not d.startswith("_")]
                
                if sub_dirs:
                    # Es una Fase que contiene emociones (ej: Base/Neutral)
                    phase_name = item
                    if phase_name not in char_entry["phases"]:
                        char_entry["phases"][phase_name] = {}

                    for emo in sub_dirs:
                        emo_path = os.path.join(item_path, emo)
                        imgs = [f for f in sorted(os.listdir(emo_path)) if f.lower().endswith(valid_exts)]
                        if imgs:
                            char_entry["phases"][phase_name][emo] = {
                                "count": len(imgs),
                                "path": emo_path
                            }
                            char_entry["total_images"] += len(imgs)
                            total_imgs += len(imgs)
                else:
                    # Es una carpeta con imágenes directas
                    # Si el nombre coincide con una emoción conocida, se asume Fase "Base"
                    clean_item = clean_string(item)
                    mapped_emo = EMOTION_ALIASES.get(clean_item, item)
                    
                    imgs = [f for f in sorted(os.listdir(item_path)) if f.lower().endswith(valid_exts)]
                    if imgs:
                        phase_name = "Base"
                        if phase_name not in char_entry["phases"]:
                            char_entry["phases"][phase_name] = {}
                        
                        char_entry["phases"][phase_name][mapped_emo] = {
                            "count": len(imgs),
                            "path": item_path
                        }
                        char_entry["total_images"] += len(imgs)
                        total_imgs += len(imgs)

            if char_entry["total_images"] > 0:
                catalog["characters"][char_name] = char_entry

        # 2. Escanear Escenarios
        if self.scens_dir and os.path.exists(self.scens_dir):
            for scen_name in sorted(os.listdir(self.scens_dir)):
                scen_path = os.path.join(self.scens_dir, scen_name)
                if not os.path.isdir(scen_path) or scen_name.startswith("_"):
                    continue
                imgs = [f for f in sorted(os.listdir(scen_path)) if f.lower().endswith(valid_exts)]
                if imgs:
                    catalog["scenarios"][scen_name] = {
                        "count": len(imgs),
                        "path": scen_path
                    }

        catalog["stats"]["total_characters"] = len(catalog["characters"])
        catalog["stats"]["total_images"] = total_imgs

        return catalog

    def save_catalog(self) -> None:
        """Guarda el catálogo en disco en formato JSON."""
        try:
            os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
            with open(self.catalog_path, "w", encoding="utf-8") as f:
                json.dump(self.catalog, f, indent=2, ensure_ascii=False)
            print(f"[+] Catalogo guardado exitosamente en: {self.catalog_path}")
        except Exception as e:
            print(f"[!] Error al guardar catalogo: {e}")

    def load_or_build_catalog(self, force_refresh: bool = False) -> None:
        """Carga el catálogo desde JSON si existe; de lo contrario, lo construye."""
        if not force_refresh and os.path.exists(self.catalog_path):
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    self.catalog = json.load(f)
                # Validar versión y ruta
                if self.catalog.get("version") == "2.0" and self.catalog.get("root_dir") == self.root_dir:
                    return
            except Exception:
                pass

        # Construir y guardar
        self.catalog = self.build_catalog()
        self.save_catalog()

    def resolve_canonical_character(self, char_raw: str) -> Optional[str]:
        """Resuelve el nombre canónico de la carpeta de un personaje."""
        if not char_raw:
            return None
        clean = clean_string(char_raw)
        
        # 1. Búsqueda por alias
        if clean in CHARACTER_ALIASES:
            clean = clean_string(CHARACTER_ALIASES[clean])

        # 2. Búsqueda exacta en catálogo
        for c_name in self.catalog.get("characters", {}).keys():
            if clean_string(c_name) == clean:
                return c_name

        # 3. Búsqueda parcial
        for c_name in self.catalog.get("characters", {}).keys():
            clean_c = clean_string(c_name)
            if clean in clean_c or clean_c in clean:
                return c_name

        return None

    def get_available_emotions(self, character: str, phase: str = "Base") -> List[str]:
        """Devuelve la lista de emociones que realmente existen para un personaje y fase."""
        char_name = self.resolve_canonical_character(character)
        if not char_name or char_name not in self.catalog.get("characters", {}):
            return []

        phases = self.catalog["characters"][char_name].get("phases", {})
        
        # Normalizar fase
        clean_p = clean_string(phase)
        target_phase = PHASE_ALIASES.get(clean_p, phase)

        if target_phase in phases:
            return sorted(list(phases[target_phase].keys()))
        elif "Base" in phases:
            return sorted(list(phases["Base"].keys()))
        elif phases:
            # Primera fase disponible
            first_phase = next(iter(phases))
            return sorted(list(phases[first_phase].keys()))
        return []

    def get_available_phases(self, character: str) -> List[str]:
        """Devuelve la lista de fases/transformaciones que existen para un personaje."""
        char_name = self.resolve_canonical_character(character)
        if not char_name or char_name not in self.catalog.get("characters", {}):
            return []
        return sorted(list(self.catalog["characters"][char_name].get("phases", {}).keys()))

    def _next_image_from_path(self, dir_path: str) -> Optional[str]:
        """Obtiene la siguiente imagen del pool para rotación uniforme sin repetición."""
        if dir_path not in self.pools:
            files = []
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                files = [
                    os.path.join(dir_path, f)
                    for f in sorted(os.listdir(dir_path))
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
                ]
            self.pools[dir_path] = {"files": files, "idx": 0}

        pool = self.pools[dir_path]
        if not pool["files"]:
            return None
        img = pool["files"][pool["idx"] % len(pool["files"])]
        pool["idx"] += 1
        return img

    def resolve_asset(
        self,
        character: str,
        phase: str = "Base",
        emotion: str = "Neutral"
    ) -> Tuple[Optional[str], str]:
        """
        Resuelve una imagen garantizando Zero-Crash mediante el Grafo Semántico de Fallback.
        
        Retorna:
            (ruta_imagen, resolución_info): Tupla con la ruta del archivo y detalle del nivel de fallback usado.
        """
        char_name = self.resolve_canonical_character(character)
        if not char_name:
            goku_img, _ = self.resolve_asset("Goku", "Base", "Neutral")
            return goku_img, f"EMERGENCY_FALLBACK_GOKU (Personaje desconocido: {character})"

        char_data = self.catalog.get("characters", {}).get(char_name)
        if not char_data or not char_data.get("phases"):
            # Si el personaje no tiene imágenes, fallback a Goku
            goku_img, _ = self.resolve_asset("Goku", "Base", "Neutral")
            return goku_img, f"EMERGENCY_FALLBACK_GOKU (Personaje sin imágenes: {char_name})"

        phases = char_data["phases"]

        # Normalizar fase y emoción solicitadas
        norm_phase = PHASE_ALIASES.get(clean_string(phase), phase)
        norm_emo = EMOTION_ALIASES.get(clean_string(emotion), emotion)

        # 1. Determinar fase efectiva a usar (si la fase pedida no existe, usar Base o primera disponible)
        effective_phase = norm_phase
        if effective_phase not in phases:
            if "Base" in phases:
                effective_phase = "Base"
            else:
                effective_phase = next(iter(phases))

        phase_emotions = phases[effective_phase]

        # 2. Búsqueda exacta: Fase efectiva + Emoción exacta
        if norm_emo in phase_emotions:
            path = phase_emotions[norm_emo]["path"]
            img = self._next_image_from_path(path)
            if img:
                return img, f"EXACT: {char_name}/{effective_phase}/{norm_emo}"

        # 3. Aplicar Grafo Semántico de Fallback en la misma fase
        fallback_chain = SEMANTIC_EMOTION_FALLBACKS.get(norm_emo, ["Neutral"])
        for fb_emo in fallback_chain:
            if fb_emo in phase_emotions:
                path = phase_emotions[fb_emo]["path"]
                img = self._next_image_from_path(path)
                if img:
                    return img, f"SEMANTIC_FALLBACK: {char_name}/{effective_phase}/{fb_emo} (Pedido: {norm_emo})"

        # 4. Fallback a Neutral en la misma fase
        if "Neutral" in phase_emotions:
            path = phase_emotions["Neutral"]["path"]
            img = self._next_image_from_path(path)
            if img:
                return img, f"PHASE_NEUTRAL_FALLBACK: {char_name}/{effective_phase}/Neutral"

        # 5. Fallback a Base/{norm_emo} si estábamos en otra fase
        if effective_phase != "Base" and "Base" in phases:
            base_emotions = phases["Base"]
            if norm_emo in base_emotions:
                img = self._next_image_from_path(base_emotions[norm_emo]["path"])
                if img:
                    return img, f"BASE_PHASE_FALLBACK: {char_name}/Base/{norm_emo}"
            for fb_emo in fallback_chain:
                if fb_emo in base_emotions:
                    img = self._next_image_from_path(base_emotions[fb_emo]["path"])
                    if img:
                        return img, f"BASE_SEMANTIC_FALLBACK: {char_name}/Base/{fb_emo}"
            if "Neutral" in base_emotions:
                img = self._next_image_from_path(base_emotions["Neutral"]["path"])
                if img:
                    return img, f"BASE_NEUTRAL_FALLBACK: {char_name}/Base/Neutral"

        # 6. Fallback a cualquier emoción existente en la fase actual o Base
        for emo_entry in phase_emotions.values():
            img = self._next_image_from_path(emo_entry["path"])
            if img:
                return img, f"ANY_EMOTION_FALLBACK: {char_name}/{effective_phase}"

        # 7. Fallback de Emergencia a Goku Base Neutral
        if char_name != "Goku":
            goku_img, _ = self.resolve_asset("Goku", "Base", "Neutral")
            if goku_img:
                return goku_img, f"CROSS_CHAR_FALLBACK_GOKU (Para {char_name})"

        return None, "NO_IMAGE_AVAILABLE"

    def generate_ai_prompt_context(self) -> str:
        """
        Genera el bloque de contexto estructurado para inyectar en el prompt del LLM o nodo IA.
        Le indica a la IA con precisión matemática qué emociones y fases existen para cada personaje.
        """
        lines = [
            "### GUÍA DE ESTADOS Y EMOCIONES DISPONIBLES POR PERSONAJE",
            "Cuando asignes etiquetas de emoción a los diálogos, utiliza ÚNICAMENTE los estados disponibles reales:",
            ""
        ]

        chars = self.catalog.get("characters", {})
        for char_name in sorted(chars.keys()):
            char_data = chars[char_name]
            phases = char_data.get("phases", {})
            if not phases:
                continue

            phase_strs = []
            for p_name, emos in phases.items():
                emo_list = sorted(list(emos.keys()))
                phase_strs.append(f"{p_name}: [{', '.join(emo_list)}]")

            lines.append(f"- **{char_name}**: " + " | ".join(phase_strs))

        lines.append("")
        lines.append("Si un diálogo requiere una acción especial (ej. combate o herido) pero el personaje no la tiene, "
                     "asigna 'Neutral' o 'Enfadado', el motor aplicará redirección semántica automática.")
        return "\n".join(lines)


# Singleton accesible globalmente
_GLOBAL_REGISTRY: Optional[DatasetRegistry] = None

def get_registry(root_dir: Optional[str] = None) -> DatasetRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None or (root_dir and _GLOBAL_REGISTRY.root_dir != root_dir):
        _GLOBAL_REGISTRY = DatasetRegistry(root_dir)
    return _GLOBAL_REGISTRY
