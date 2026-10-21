"""fabric-xl-fix: repair the MIDI aftertouch-depth issue in AIR Fabric XL presets."""

from .core import (
    PresetFormatError,
    decode_state,
    encode_state,
    fix_preset_text,
    fix_state_bytes,
    guess_preset_name,
)

__all__ = [
    "PresetFormatError",
    "decode_state",
    "encode_state",
    "fix_preset_text",
    "fix_state_bytes",
    "guess_preset_name",
]

__version__ = "1.0.0"
