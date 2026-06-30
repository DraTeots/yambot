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
TEMPLATE_CONFIRM_BUTTON = TEMPLATES_DIR / "confirm_button.png"
TEMPLATE_MAP_SEPARATOR: Path = TEMPLATES_DIR / "island_list_separator.png"
#: The map button on an island that returns to the world map.
TEMPLATE_MAP_BUTTON = TEMPLATES_DIR / "map_button.png"

# --- Resource collection (key 5) ------------------------------------------
# Markers the map list draws on an island's row when it has resources ready to
# collect. We scan the island list for either; their absence is the signal that
# an island has nothing waiting.
TEMPLATE_MAP_HAS_CRYSTALS = TEMPLATES_DIR / "map_has_crystals.png"
TEMPLATE_MAP_HAS_MONEY = TEMPLATES_DIR / "map_has_money.png"

# --- Friends list ---------------------------------------------------------
# The list pager has back/next buttons that share a shape per direction and
# differ only in tone (enabled vs. greyed), so each comes as an active/inactive
# pair fed to check_is_active. The quick-light button only exists when there's
# a torch to light — its absence is the signal, not a separate "off" image.
TEMPLATE_FRIEND_BACK_ACTIVE = TEMPLATES_DIR / "friend_list_back_active_button.png"
TEMPLATE_FRIEND_BACK_INACTIVE = TEMPLATES_DIR / "friend_list_back_inactive_button.png"
TEMPLATE_FRIEND_NEXT_ACTIVE = TEMPLATES_DIR / "friend_list_next_active_button.png"
TEMPLATE_FRIEND_NEXT_INACTIVE = TEMPLATES_DIR / "friend_list_next_inactive_button.png"
TEMPLATE_FRIEND_QUICK_LIGHT = TEMPLATES_DIR / "friend_quick_light_active.png"

# Advanced flow: light each friend individually. The list-side light button has
# an active/inactive pair (already-lit friends read inactive). Lighting one opens
# that friend's map, where we hunt the on-map light + go buttons and navigate
# back via the close / island buttons.
TEMPLATE_FRIEND_LIGHT_ACTIVE = TEMPLATES_DIR / "friend_light_active.png"
TEMPLATE_FRIEND_LIGHT_INACTIVE = TEMPLATES_DIR / "friend_light_inactive.png"
#: The light button on a friend's own map — same image whether reached from the
#: map view or after pressing Go onto their island.
TEMPLATE_FRIEND_LIGHT = TEMPLATES_DIR / "friend_light.png"
TEMPLATE_FRIEND_MAP_CLOSE = TEMPLATES_DIR / "friend_map_close_button.png"
TEMPLATE_FRIEND_ISLAND_BUTTON = TEMPLATES_DIR / "friend_island_button.png"
TEMPLATE_GO_BUTTON = TEMPLATES_DIR / "go_button.png"
#: Sometimes a friend's map opens zoomed into a sub-island; this button returns
#: to their main map before we hunt for the fire.
TEMPLATE_MAP_GO_TO_MAIN_WORLD = TEMPLATES_DIR / "map_go_main_world_button.png"
TEMPLATE_MAP_GO_TO_MIRROR_WORLD = TEMPLATES_DIR / "map_go_mirror_world_button.png"

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
