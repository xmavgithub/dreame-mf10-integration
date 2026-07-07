"""Constants for the Dreame MF10 integration."""

from __future__ import annotations

DOMAIN = "dreame_mf10"

MODEL_MF10 = "dreame.fan.u2519"
SUPPORTED_MODELS = {MODEL_MF10}

CONF_REGION = "region"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_DEBUG_PROPERTY_SCAN = "debug_property_scan"
CONF_EXPERIMENTAL_ENTITIES = "experimental_entities"

REGION_OPTIONS = ["eu", "cn", "us", "sg", "ru", "kr"]
DEFAULT_REGION = "eu"

DEFAULT_POLLING_INTERVAL = 30
MIN_POLLING_INTERVAL = 10
MAX_POLLING_INTERVAL = 300

MF10_SPEED_MIN = 1
MF10_SPEED_MAX = 10

PLATFORMS: list[str] = ["sensor", "fan", "switch", "select"]

MF10_POWER_ON = 1
MF10_POWER_OFF = 2

# Provisional MiOT property candidates for dreame.fan.u2519.
# These are NOT validated — confirm against the device before promoting them into
# MF10_PROPERTY_MAP.
MF10_PROPERTY_CANDIDATES: dict[str, list[dict[str, int]]] = {
    # Confirmed (see docs/property_map.md)
    "power": [{"siid": 2, "piid": 1}],
    "mode": [{"siid": 2, "piid": 3}],
    "fan_speed": [{"siid": 2, "piid": 4}],
    "child_lock": [{"siid": 2, "piid": 5}],
    "temperature": [{"siid": 3, "piid": 2}],
    # Unconfirmed — oscillation and other controls
    "unknown_2_2": [{"siid": 2, "piid": 2}],
    "oscillation_candidates": [
        {"siid": 2, "piid": 7},
        {"siid": 2, "piid": 8},
        {"siid": 2, "piid": 10},
        {"siid": 2, "piid": 11},
        {"siid": 2, "piid": 12},
    ],
    "siid6_candidates": [
        {"siid": 6, "piid": 1},
        {"siid": 6, "piid": 2},
        {"siid": 6, "piid": 3},
        {"siid": 6, "piid": 4},
        {"siid": 6, "piid": 6},
        {"siid": 6, "piid": 7},
    ],
}

# Canonical, validated MiOT property map for dreame.fan.u2519.
# Updated for firmware 1043 / plugin 116 (2026-06-05).
# These are the (siid, piid) used for production polling and entity state.
MF10_PROPERTY_MAP: dict[str, dict] = {
    "power": {"siid": 2, "piid": 1},                  # 1=ON, 2=OFF — read-only
    "mode": {"siid": 2, "piid": 3},                   # 0=AI auto, 1=Potente, 2=Sonno, 3=Manuale, 7=Naturale
    "fan_speed": {"siid": 2, "piid": 4},              # int 1–10
    "child_lock": {"siid": 6, "piid": 10},            # 0=OFF, 1=ON — moved from (2,5) in fw1043
    "blade_oscillation": {"siid": 2, "piid": 8},      # 0=none, 1=left, 2=right, 3=both — moved from (2,6) in fw1043
    "device_rotation": {"siid": 2, "piid": 7},        # 0=off, 1=on
    "sync_oscillation": {"siid": 2, "piid": 9},       # 0=off, 1=on — moved from (2,11) in fw1043
    "staggered_oscillation": {"siid": 2, "piid": 12}, # 0=off, 1=on — confirmed fw1043
    "temperature": {"siid": 3, "piid": 2},            # °C, read-only sensor
    # REMOVED fw1043: continuous_monitoring (2,10) — semantics changed (reads 1 or 2, never 0); behaviour unconfirmed
    # REMOVED fw1043: key_tone (6,7) — returns 80001 when off, breaks batch polling
    # REMOVED fw1043: display (6,11) — reassigned to timezone string
    # REMOVED fw1043: off_timer — (2,8) is now blade_oscillation; timer location unknown
}

# Properties present but NOT yet identified:
#   (2, 2) — always 0 across all modes and states
#   (2, 7) — always 0 across all oscillation tests; purpose unknown
#   (2, 8) — always 0
#   (2, 10) — always 1
#   (6, 4) — always 0
#   (6, 7) — always 1 (NOT child_lock; possibly buzzer or display)
# System read-only (not polled):
#   (6, 1) — timezone string e.g. "Europe/Rome"
#   (6, 2) — empty string (device name?)

# Blade oscillation enum values (for MF10_PROPERTY_MAP["blade_oscillation"])
MF10_BLADE_OSC_NONE = 0
MF10_BLADE_OSC_LEFT = 1
MF10_BLADE_OSC_RIGHT = 2
MF10_BLADE_OSC_BOTH = 3

# Fan mode enum values (for MF10_PROPERTY_MAP["mode"])
MF10_MODE_AI = 0
MF10_MODE_POWERFUL = 1
MF10_MODE_NIGHT = 2
MF10_MODE_MANUAL = 3
MF10_MODE_NATURAL = 7

MF10_MODE_OPTIONS: dict[int, str] = {
    MF10_MODE_AI: "ai",
    MF10_MODE_POWERFUL: "powerful",
    MF10_MODE_NIGHT: "night",
    MF10_MODE_MANUAL: "manual",
    MF10_MODE_NATURAL: "natural",
}
MF10_MODE_NAME_TO_VALUE: dict[str, int] = {v: k for k, v in MF10_MODE_OPTIONS.items()}

# Unified oscillation select — composes blade_oscillation (2,8) +
# sync_oscillation (2,9) + staggered_oscillation (2,12) into a single
# coherent state. sync/staggered are only meaningful with both blades active.
# NOTE fw1043: sync moved from (2,11) to (2,9).
MF10_OSC_OFF = "off"                       # blade=0
MF10_OSC_LEFT = "left"                     # blade=1, sync=0, staggered=0
MF10_OSC_RIGHT = "right"                   # blade=2, sync=0, staggered=0
MF10_OSC_BOTH_INDEPENDENT = "both"          # blade=3, sync=0, staggered=0
MF10_OSC_BOTH_SYNCHRONIZED = "both_sync"    # blade=3, sync=1, staggered=0
MF10_OSC_BOTH_STAGGERED = "both_staggered"  # blade=3, sync=0, staggered=1
MF10_OSC_OPTIONS: list[str] = [
    MF10_OSC_OFF,
    MF10_OSC_LEFT,
    MF10_OSC_RIGHT,
    MF10_OSC_BOTH_INDEPENDENT,
    MF10_OSC_BOTH_SYNCHRONIZED,
    MF10_OSC_BOTH_STAGGERED,
]

# (blade, sync, staggered) tuple for each option, used to write to the device.
MF10_OSC_TO_PROPS: dict[str, tuple[int, int, int]] = {
    MF10_OSC_OFF: (MF10_BLADE_OSC_NONE, 0, 0),
    MF10_OSC_LEFT: (MF10_BLADE_OSC_LEFT, 0, 0),
    MF10_OSC_RIGHT: (MF10_BLADE_OSC_RIGHT, 0, 0),
    MF10_OSC_BOTH_INDEPENDENT: (MF10_BLADE_OSC_BOTH, 0, 0),
    MF10_OSC_BOTH_SYNCHRONIZED: (MF10_BLADE_OSC_BOTH, 1, 0),
    MF10_OSC_BOTH_STAGGERED: (MF10_BLADE_OSC_BOTH, 0, 1),
}

