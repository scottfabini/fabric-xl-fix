import base64
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fabric_xl_fix.core import (
    PresetFormatError,
    decode_state,
    encode_state,
    fix_preset_text,
    fix_state_bytes,
    guess_preset_name,
)

FIXTURES = Path(__file__).parent / "fixtures"


def make_xpl(state: str, include_preset_tag: bool = False) -> str:
    preset_line = "  <preset>Test Preset</preset>\r\n" if include_preset_tag else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        "\r\n"
        "<pluginstate>\r\n"
        '  <version file="1" date="2021-01-01-00-00"/>\r\n'
        '  <PLUGIN name="Fabric XL" format="MPC" category="Synth" manufacturer="AIR Music Technology"\r\n'
        '          version="" file="MPC:FabricXL" uid="46627258" isInstrument="1"\r\n'
        '          fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2"\r\n'
        '          isShell="0"/>\r\n'
        f"{preset_line}"
        f"  <state>{state}</state>\r\n"
        "</pluginstate>\r\n"
    )


def encode_raw(data: bytes) -> str:
    """A plain, spec-correct base64 encode (no filler-bit trick), used to
    build synthetic test fixtures independent of our own encoder."""
    b64 = base64.b64encode(data).decode("ascii").rstrip("=")
    return b64.replace("/", ".")


class RoundTripTests(unittest.TestCase):
    def test_decode_encode_round_trip_multiple_of_three(self):
        data = bytes(range(30))  # 30 bytes, divisible by 3
        state = f"{len(data)}.{encode_raw(data)}"
        xpl = make_xpl(state)
        self.assertEqual(decode_state(xpl), data)
        self.assertEqual(encode_state(data), state)

    def test_decode_encode_round_trip_remainder_one(self):
        data = bytes(range(31))  # 31 % 3 == 1
        # Can't build this fixture with plain base64 since the filler
        # bits differ; instead round-trip through our own encoder and
        # confirm decode(encode(x)) == x.
        state = encode_state(data)
        xpl = make_xpl(state)
        self.assertEqual(decode_state(xpl), data)

    def test_decode_encode_round_trip_remainder_two(self):
        data = bytes(range(32))  # 32 % 3 == 2
        state = encode_state(data)
        xpl = make_xpl(state)
        self.assertEqual(decode_state(xpl), data)

    def test_missing_state_raises(self):
        with self.assertRaises(PresetFormatError):
            decode_state("<pluginstate></pluginstate>")

    def test_length_mismatch_raises(self):
        data = bytes(range(10))
        bad_state = f"999.{encode_raw(data)}"
        with self.assertRaises(PresetFormatError):
            decode_state(make_xpl(bad_state))


class FixLogicTests(unittest.TestCase):
    def _bad_state_bytes(self, length=1272):
        # Deterministic pseudo-random-looking bytes standing in for a
        # real factory preset's binary state.
        data = bytearray((i * 37 + 11) % 256 for i in range(length))
        return bytes(data)

    def test_universal_fix_applied(self):
        data = self._bad_state_bytes()
        fixed = fix_state_bytes(data)
        self.assertEqual(fixed[991:1000], bytes.fromhex("ffd6389bceffffffff"))

    def test_aftertouch_depth_cleared_at_both_offsets(self):
        data = self._bad_state_bytes()
        fixed = fix_state_bytes(data)
        self.assertEqual(fixed[88:90], b"\xff\xff")
        self.assertEqual(fixed[91:93], b"\xff\xff")

    def test_untouched_bytes_are_preserved(self):
        data = self._bad_state_bytes()
        fixed = fix_state_bytes(data)
        touched = set(range(991, 1000)) | {88, 89, 91, 92}
        for i in range(len(data)):
            if i not in touched:
                self.assertEqual(fixed[i], data[i], f"byte {i} should be untouched")

    def test_short_state_is_not_out_of_bounds(self):
        # Preset shorter than the fix regions should be returned as-is,
        # not raise an IndexError.
        data = bytes(range(50))
        fixed = fix_state_bytes(data)
        self.assertEqual(fixed, data)

    def test_fix_preset_text_adds_missing_preset_tag(self):
        data = self._bad_state_bytes()
        xpl = make_xpl(encode_state(data), include_preset_tag=False)
        result = fix_preset_text(xpl, preset_name_hint="My Preset")
        self.assertIn("<preset>My Preset</preset>", result.text)
        self.assertTrue(result.changed)

    def test_fix_preset_text_keeps_existing_preset_tag(self):
        data = self._bad_state_bytes()
        xpl = make_xpl(encode_state(data), include_preset_tag=True)
        result = fix_preset_text(xpl, preset_name_hint="Ignored")
        self.assertEqual(result.text.count("<preset>"), 1)
        self.assertIn("<preset>Test Preset</preset>", result.text)

    def test_fix_preset_text_is_idempotent(self):
        data = self._bad_state_bytes()
        xpl = make_xpl(encode_state(data), include_preset_tag=True)
        once = fix_preset_text(xpl, preset_name_hint="Test Preset")
        twice = fix_preset_text(once.text, preset_name_hint="Test Preset")
        self.assertEqual(once.text, twice.text)
        self.assertFalse(twice.changed)

    def test_line_endings_preserved(self):
        data = self._bad_state_bytes()
        xpl = make_xpl(encode_state(data), include_preset_tag=False)
        result = fix_preset_text(xpl, preset_name_hint="CRLF Preset")
        for line in result.text.split("\n")[:-1]:
            self.assertTrue(line.endswith("\r"), f"line not CRLF-terminated: {line!r}")


class GuessPresetNameTests(unittest.TestCase):
    def test_numbered_category_filename(self):
        self.assertEqual(
            guess_preset_name("0104-Pianos-Atmospheric Pick.xpl"), "Atmospheric Pick"
        )

    def test_simple_numbered_filename(self):
        self.assertEqual(guess_preset_name("0000-Awakening.xpl"), "Awakening")

    def test_filename_without_separators(self):
        self.assertEqual(guess_preset_name("PlainName.xpl"), "PlainName")


if __name__ == "__main__":
    unittest.main()
