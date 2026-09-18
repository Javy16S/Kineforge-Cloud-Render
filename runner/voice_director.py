"""
KineForge Cloud Pipeline - Master Voice Director & Character Registry
Define la asignación de voces entre Fish Audio SOTA y modelos RVC locales/nube.

Voces Base Fish Audio configuradas por el usuario:
- Narrador: 3f45a7fd7a614655a61eb7027b955783
- Personaje masculino 1: dc0746cd45dd40deb6bca32dc87fd7f5 (Grave / Imponente / Villano)
- Personaje masculino 2: f4210324af9d4a28a9cfe15f74a9cd84 (Serio / Rival / Tenso)
- Personaje masculino 3: dfa5b230c8054f429e434f4a6e9bbdec (Heroico / Enérgico - "Voz muy buena")
- Personaje masculino 4: dfa5b230c8054f429e434f4a6e9bbdec (Juvenil / Rápido)
- Personaje femenino 1: bfed5c0810a347dbb62e8ccce7f59c48 (Joven / Expresiva / Alegre)
- Personaje femenino 2: e296306da5d449999f6e35c2b9f60aea (Madura / Serena / Fría)
- Personaje femenino medio: e296306da5d449999f6e35c2b9f60aea (Técnica / Misteriosa)
"""

import os
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

FISH_CATALOG = {
    "narrador": "3f45a7fd7a614655a61eb7027b955783",
    "masculino_1": "dc0746cd45dd40deb6bca32dc87fd7f5",
    "masculino_2": "f4210324af9d4a28a9cfe15f74a9cd84",
    "masculino_3": "b6054754fb8041f8ae2d146f8a77d426",  # Ippo Makunouchi (Doblaje Latino Heroico)
    "masculino_4": "b6054754fb8041f8ae2d146f8a77d426",
    "femenino_1": "bfed5c0810a347dbb62e8ccce7f59c48",
    "femenino_2": "e296306da5d449999f6e35c2b9f60aea",
    "femenino_medio": "e296306da5d449999f6e35c2b9f60aea"
}

# Registro Maestro de Personajes: Mapeo de Personaje -> (Voz Fish Audio, Modo [direct/rvc], Modelo RVC, Semitonos Pitch)
CHARACTER_REGISTRY = {
    # 🎙️ NARRACIÓN (100% Pura Fish Audio SOTA)
    "Narrador": {
        "fish_id": FISH_CATALOG["narrador"],
        "mode": "direct",
        "rvc_model": None,
        "pitch": 0,
        "role": "Narrador Épico Dragon Ball"
    },

    # ⚔️ PROTAGONISTAS HEROICOS (Masculino 3 - Ippo Doblaje Latino)
    # Calibración de volumen: +6.5 dB para igualar potencia acústica al Narrador
    "Goku": {
        "fish_id": FISH_CATALOG["masculino_3"],
        "mode": "direct",
        "rvc_model": None,
        "pitch": 0,
        "gain_db": 6.5,
        "role": "Guerrero Saiyajin Heroico"
    },
    "Luffy": {
        "fish_id": FISH_CATALOG["masculino_3"],
        "mode": "direct",
        "rvc_model": None,
        "pitch": 0,
        "gain_db": 6.0,
        "role": "Capitán Pirata Enérgico"
    },
    "Gohan": {
        "fish_id": FISH_CATALOG["masculino_3"],
        "mode": "direct",
        "rvc_model": None,
        "pitch": 0,
        "gain_db": 6.0,
        "role": "Héroe Híbrido Noble"
    },
    "Trunks": {
        "fish_id": FISH_CATALOG["masculino_4"],
        "mode": "direct",
        "rvc_model": None,
        "pitch": 0,
        "gain_db": 6.0,
        "role": "Guerrero del Futuro"
    },

    # ⚡ RIVALES Y SERIOS (Masculino 2)
    "Vegeta": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Vegeta",
        "pitch": 0,
        "role": "Príncipe de los Saiyajin Orgulloso"
    },
    "Zoro": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Zoro",
        "pitch": 0,
        "role": "Espadachín Silencioso y Letal"
    },
    "Piccolo": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Piccolo",
        "pitch": -2,
        "role": "Sabio Namekiano Estratega"
    },
    "Sanji": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Sanji",
        "pitch": 0,
        "role": "Caballero Cocinero Elegante"
    },
    "Shanks": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Shanks",
        "pitch": 0,
        "role": "Emperador Pirata Pelirrojo"
    },

    # 💥 IMPONENTES, VILLANOS Y ANCIANOS (Masculino 1)
    "Broly": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "rvc",
        "rvc_model": "Gerardo_Vasquez",
        "pitch": -2,
        "role": "Super Saiyajin Legendario Furia"
    },
    "Cell": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "rvc",
        "rvc_model": "Gerardo_Vasquez",
        "pitch": 0,
        "role": "Bio-Androide Perfecto"
    },
    "Freezer": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Freezer",
        "pitch": +2,
        "role": "Emperador del Mal Arrogante"
    },
    "Bills_Beerus": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Bills",
        "pitch": -1.5,
        "gain_db": 4.5,
        "role": "Dios de la Destrucción Imponente"
    },
    "Beerus": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Bills",
        "pitch": -1.5,
        "gain_db": 4.5,
        "role": "Dios de la Destrucción Imponente"
    },
    "Bills": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Bills",
        "pitch": -1.5,
        "gain_db": 4.5,
        "role": "Dios de la Destrucción Imponente"
    },
    "Whis": {
        "fish_id": FISH_CATALOG["masculino_2"],
        "mode": "direct",
        "rvc_model": "Whis",
        "pitch": +2.5,
        "gain_db": 5.0,
        "role": "Ángel Guía Aristocrático y Refinado"
    },
    "Muten_Roshi": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "MutenRoshi",
        "pitch": -1,
        "role": "Maestro Veterano Sabio"
    },
    "Garp": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Garp",
        "pitch": -1,
        "role": "Héroe de la Marina Imponente"
    },
    "Roger": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "Roger",
        "pitch": 0,
        "role": "Rey de los Piratas Legendario"
    },
    "Mr_Satan": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "MrSatan",
        "pitch": +1,
        "role": "Campeón Exagerado"
    },
    "Imu_Sama": {
        "fish_id": FISH_CATALOG["masculino_1"],
        "mode": "direct",
        "rvc_model": "ImuSama",
        "pitch": -3,
        "role": "Soberano Supremo Oscuro"
    },

    # 🌸 PERSONAJES FEMENINOS ENÉRGICOS / JÓVENES (Femenino 1)
    "Bulma": {
        "fish_id": FISH_CATALOG["femenino_1"],
        "mode": "rvc",
        "rvc_model": "Cristina_Hernandez",
        "pitch": 0,
        "role": "Científica Brillante y Temperamental"
    },
    "Nami": {
        "fish_id": FISH_CATALOG["femenino_1"],
        "mode": "direct",
        "rvc_model": "Nami",
        "pitch": 0,
        "role": "Navegante Astuta y Enérgica"
    },
    "Videl": {
        "fish_id": FISH_CATALOG["femenino_1"],
        "mode": "rvc",
        "rvc_model": "Cristina_Hernandez",
        "pitch": 0,
        "role": "Heroína Joven de Acción"
    },
    "Chopper": {
        "fish_id": FISH_CATALOG["femenino_1"],
        "mode": "direct",
        "rvc_model": "Chopper",
        "pitch": +3,
        "role": "Médico Reno Tierno"
    },
    "Dende": {
        "fish_id": FISH_CATALOG["femenino_1"],
        "mode": "direct",
        "rvc_model": "Dende",
        "pitch": +1,
        "role": "Kami-sama Joven"
    },

    # 🌙 PERSONAJES FEMENINOS SERENOS / MADUROS (Femenino 2 / Medio)
    "Androide_18": {
        "fish_id": FISH_CATALOG["femenino_2"],
        "mode": "rvc",
        "rvc_model": "Nuria_Mediavilla",
        "pitch": 0,
        "role": "Guerrera Androide Letal y Serena"
    },
    "Robin": {
        "fish_id": FISH_CATALOG["femenino_medio"],
        "mode": "direct",
        "rvc_model": "Robin",
        "pitch": 0,
        "role": "Arqueóloga Elegante y Enigmática"
    },
    "Milk": {
        "fish_id": FISH_CATALOG["femenino_2"],
        "mode": "direct",
        "rvc_model": "Milk",
        "pitch": 0,
        "role": "Madre Protectora Firme"
    },
    "Chichi": {
        "fish_id": FISH_CATALOG["femenino_2"],
        "mode": "direct",
        "rvc_model": "Milk",
        "pitch": 0,
        "role": "Madre Protectora Firme"
    },
    "Yamato": {
        "fish_id": FISH_CATALOG["femenino_2"],
        "mode": "direct",
        "rvc_model": "Yamato",
        "pitch": 0,
        "role": "Guerrera Poderosa"
    },
    "Hancock": {
        "fish_id": FISH_CATALOG["femenino_2"],
        "mode": "direct",
        "rvc_model": "Hancock",
        "pitch": 0,
        "role": "Emperatriz Pirata Majestuosa"
    },

    # 🎭 SECUNDARIOS EXPRESIVOS (Masculino 3 / 4)
    "Krilin": {
        "fish_id": FISH_CATALOG["masculino_3"],
        "mode": "direct",
        "rvc_model": "Krilin",
        "pitch": +2,
        "role": "Compañero Valiente"
    },
    "Usopp": {
        "fish_id": FISH_CATALOG["masculino_4"],
        "mode": "direct",
        "rvc_model": "Usopp",
        "pitch": +1,
        "role": "Francotirador Expresivo"
    }
}

def resolve_character_voice(char_name):
    """
    Resuelve la configuración de voz para cualquier personaje del guion.
    Retorna: (fish_model_id, mode, rvc_model, pitch, role, gain_db)
    """
    c_norm = char_name.strip().replace(" ", "_")
    
    # 1. Búsqueda exacta
    if c_norm in CHARACTER_REGISTRY:
        cfg = CHARACTER_REGISTRY[c_norm]
        return cfg["fish_id"], cfg["mode"], cfg.get("rvc_model"), cfg.get("pitch", 0), cfg["role"], cfg.get("gain_db", 0.0)
    
    # 2. Búsqueda por subcadena / alias
    for k, cfg in CHARACTER_REGISTRY.items():
        if k.lower() in c_norm.lower() or c_norm.lower() in k.lower():
            return cfg["fish_id"], cfg["mode"], cfg.get("rvc_model"), cfg.get("pitch", 0), cfg["role"], cfg.get("gain_db", 0.0)
            
    # 3. Detección heurística por género
    c_lower = c_norm.lower()
    if any(f in c_lower for f in ["bulma", "videl", "milk", "chichi", "18", "androide_18", "nami", "robin", "yamato", "hancock", "mujer", "chica"]):
        cfg = CHARACTER_REGISTRY["Androide_18"]
        return cfg["fish_id"], "direct", None, 0, "Femenino Genérico", cfg.get("gain_db", 0.0)
        
    # 4. Fallback a Narrador Oficial
    cfg = CHARACTER_REGISTRY["Narrador"]
    return cfg["fish_id"], cfg["mode"], cfg.get("rvc_model"), cfg.get("pitch", 0), "Narrador / Masculino General", cfg.get("gain_db", 0.0)

def export_fish_voices_json(output_path="fish_voices.json"):
    """Exporta el mapeo directo Personaje -> fish_model_id para consumo rápido en la nube"""
    mapping = {k: v["fish_id"] for k, v in CHARACTER_REGISTRY.items()}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    return mapping

if __name__ == "__main__":
    out_file = os.path.join(os.path.dirname(__file__), "fish_voices.json")
    mapping = export_fish_voices_json(out_file)
    print(f"✅ Exportadas {len(mapping)} voces a {out_file}")
