"""Filesystem paths to the template images yambot matches against.

This module is the single place that knows *where the pictures live*. Keeping
the paths out of :mod:`yambot.screen` means the matching logic and the asset
catalogue can change independently — add a new island here without touching the
eyes. Everything is a :class:`pathlib.Path` so callers can pass them straight to
:func:`yambot.screen.find_on_image`.
"""

from pathlib import Path

#: Package root (the directory this file sits in).
_PKG_DIR = Path(__file__).parent

#: Top-level template folder and the island sub-folder.
TEMPLATES_DIR = _PKG_DIR / "templates"
MAP_ISLANDS_DIR = TEMPLATES_DIR / "map_islands"

# --- UI buttons -----------------------------------------------------------
TEMPLATE_ISL_COLLECT_BUTTON = TEMPLATES_DIR / "collect_all.png"
TEMPLATE_ISL_CLOSE_BUTTON = TEMPLATES_DIR / "close_button.png"
TEMPLATE_MAP_SEPARATOR: Path = TEMPLATES_DIR / "island_list_separator.png"

# --- Map islands ----------------------------------------------------------
# Keyed by island so callers read like the game's own labels. The numeric
# prefix preserves the in-game order; ``_v1`` is the template revision.
ISLANDS_MAIN = {
    "plant": MAP_ISLANDS_DIR / "main_01_plant_v1.png",
    "cold": MAP_ISLANDS_DIR / "main_02_cold_v1.png",
    "air": MAP_ISLANDS_DIR / "main_03_air_v1.png",
    "water": MAP_ISLANDS_DIR / "main_04_water_v1.png",
    "earth": MAP_ISLANDS_DIR / "main_05_earth_v1.png",
    "shugabush": MAP_ISLANDS_DIR / "main_06_shugabush_v1.png",
    "colossingum": MAP_ISLANDS_DIR / "main_07_colossingum_v1.png",
    "gold": MAP_ISLANDS_DIR / "main_08_gold_v1.png",
    "ethereal": MAP_ISLANDS_DIR / "main_09_ethereal_v1.png",
    "eworkshop": MAP_ISLANDS_DIR / "main_10_eworkshop_v1.png",
    "haven": MAP_ISLANDS_DIR / "main_11_haven_v1.png",
    "oasis": MAP_ISLANDS_DIR / "main_12_oasis_v1.png",
    "mythical": MAP_ISLANDS_DIR / "main_13_mythical_v1.png",
    "light": MAP_ISLANDS_DIR / "main_14_light_v1.png",
    "psychic": MAP_ISLANDS_DIR / "main_15_psychic_v1.png",
    "faerie": MAP_ISLANDS_DIR / "main_16_faerie_v1.png",
    "bone": MAP_ISLANDS_DIR / "main_17_bone_v1.png",
    "sanctum": MAP_ISLANDS_DIR / "main_18_sanctum_v1.png",
    "nexus": MAP_ISLANDS_DIR / "main_19_nexus_v1.png",
    "carnival": MAP_ISLANDS_DIR / "main_20_carnival_v1.png",
    "seasonal": MAP_ISLANDS_DIR / "main_21_seasonal_v1.png",
    "amber": MAP_ISLANDS_DIR / "main_22_amber_v1.png",
    "wublin": MAP_ISLANDS_DIR / "main_23_wublin_v1.png",
    "celestial": MAP_ISLANDS_DIR / "main_24_celestial_v1.png",
}

#: Mirror-world counterparts (only the ones captured so far).
ISLAND_MIRROR = {
    "plant": MAP_ISLANDS_DIR / "mirror_01_plant.png",
    "cold": MAP_ISLANDS_DIR / "mirror_02_cold.png",
}

#: Convenience aliases for the islands referenced directly by the main loop.
TEMPLATE_MAP_MAIN_PLANT = ISLANDS_MAIN["plant"]
TEMPLATE_MAP_MAIN_COLD = ISLANDS_MAIN["cold"]
TEMPLATE_MAP_MAIN_AIR = ISLANDS_MAIN["air"]
