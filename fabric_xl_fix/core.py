"""Core encode/decode/transform logic for AIR Fabric XL (.xpl) presets.

Fabric XL presets are XML files with a single binary blob embedded as:

    <state>LENGTH.PAYLOAD</state>

- LENGTH is the exact byte length of the decoded binary state.
- PAYLOAD is standard base64 with three quirks:
    1. '/' is replaced with '.' (so '.' means literal '/', not "empty").
    2. Trailing '=' padding is stripped entirely - LENGTH is used to
       reconstruct it on decode.
    3. When the byte length isn't a multiple of 3, the "filler" bits of
       the last base64 character are set to 1 (not zero-filled like
       standard base64). Re-encoding without correcting for this
       produces a valid decode but a different string than the
       original, which some parsers reject.

Every stock preset shipped by AIR ships in an unmodified "factory"
state where two settings behave undesirably in practice:

- The MIDI aftertouch-depth parameter is enabled with a nonzero value
  (bytes 88-89 and/or 91-92 of the decoded state).
- A related MIDI settings block at bytes 991-999 differs from the
  value AIR's own editor writes once a preset has been touched and
  resaved.

This module applies exactly those two changes and nothing else. An
earlier, broader "disable everything MIDI-ish" heuristic was tried and
rejected: byte-level analysis across a library of 1274 factory presets
showed most of the extra positions it touched hold real, highly
variable, preset-specific synthesis parameters (not disabled toggles),
so blindly zeroing them corrupted presets. See README.md for the full
story.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

_STATE_RE = re.compile(r"<state>([^<]+)</state>")
_PLUGIN_TAG_RE = re.compile(r"(<PLUGIN\b.*?/>)", re.DOTALL)
_PRESET_NAME_RE = re.compile(r"(?:^|-)([^/-]+)\.xpl$")

# Bytes 991-999, verified byte-for-byte identical across every known
# Bad -> Fixed preset pair.
UNIVERSAL_FIX_OFFSET = 991
UNIVERSAL_FIX = bytes.fromhex("ffd6389bceffffffff")

# Aftertouch Depth is a 16-bit value that can live at either offset
# depending on the preset's parameter layout; both are set to ff ff.
AFTERTOUCH_DEPTH_OFFSETS = (88, 91)


class PresetFormatError(ValueError):
    """Raised when an .xpl file doesn't contain a recognizable <state> block."""


import base64


def decode_state(xpl_text: str) -> bytes:
    """Extract and decode the binary state blob from raw .xpl XML text."""
    match = _STATE_RE.search(xpl_text)
    if not match:
        raise PresetFormatError("no <state> element found")

    state = match.group(1)
    length_str, _, payload = state.partition(".")
    if not payload:
        raise PresetFormatError("<state> is missing its base64 payload")

    b64 = payload.replace(".", "/")
    b64 += "=" * (-len(b64) % 4)
    data = base64.b64decode(b64)

    expected_length = int(length_str)
    if len(data) != expected_length:
        raise PresetFormatError(
            f"decoded length {len(data)} does not match declared length {expected_length}"
        )
    return data


def encode_state(data: bytes) -> str:
    """Encode bytes back into a "LENGTH.PAYLOAD" state string.

    Byte-for-byte reproduces the original encoder's output (verified
    against known Bad/Fixed reference pairs), including the
    fill-bits-as-1 behavior on partial base64 groups.
    """
    full = base64.b64encode(data).decode("ascii")
    remainder = len(data) % 3

    if remainder == 0:
        b64 = full
    else:
        chars = list(full)
        if remainder == 1:
            idx, shift, fill_bits = len(full) - 3, 4, 0b1111
        else:
            idx, shift, fill_bits = len(full) - 2, 2, 0b11
        real_bits = _B64_ALPHABET.index(chars[idx]) >> shift
        chars[idx] = _B64_ALPHABET[(real_bits << shift) | fill_bits]
        b64 = "".join(chars[: idx + 1])

    return f"{len(data)}.{b64.replace('/', '.')}"


def fix_state_bytes(data: bytes) -> bytes:
    """Apply the two verified fixes to a decoded preset state."""
    result = bytearray(data)

    end = UNIVERSAL_FIX_OFFSET + len(UNIVERSAL_FIX)
    if len(result) >= end:
        result[UNIVERSAL_FIX_OFFSET:end] = UNIVERSAL_FIX

    for offset in AFTERTOUCH_DEPTH_OFFSETS:
        if len(result) > offset + 1:
            result[offset] = 0xFF
            result[offset + 1] = 0xFF

    return bytes(result)


@dataclass
class FixResult:
    changed: bool
    text: str


def fix_preset_text(xpl_text: str, preset_name_hint: str | None = None) -> FixResult:
    """Apply the fix to the raw text of an .xpl file, returning the new text.

    `preset_name_hint` is used to fill in a missing <preset> element
    (some factory presets ship without one); it's typically derived
    from the filename.
    """
    original_state_bytes = decode_state(xpl_text)
    fixed_state_bytes = fix_state_bytes(original_state_bytes)
    changed = fixed_state_bytes != original_state_bytes

    new_state = encode_state(fixed_state_bytes)
    new_text = _STATE_RE.sub(lambda _: f"<state>{new_state}</state>", xpl_text, count=1)

    if "<preset>" not in new_text and preset_name_hint:
        newline = "\r\n" if "\r\n" in xpl_text else "\n"
        new_text, n = _PLUGIN_TAG_RE.subn(
            lambda m: f"{m.group(1)}{newline}  <preset>{preset_name_hint}</preset>",
            new_text,
            count=1,
        )
        if n == 0:
            raise PresetFormatError("could not find <PLUGIN .../> to attach <preset> after")
        changed = True

    return FixResult(changed=changed, text=new_text)


def guess_preset_name(filename: str) -> str:
    """Derive a preset name from a factory filename, e.g.
    '0104-Pianos-Atmospheric Pick.xpl' -> 'Atmospheric Pick'.
    """
    match = _PRESET_NAME_RE.search(filename)
    if match:
        return match.group(1)
    return filename.rsplit(".", 1)[0]
