# fabric-xl-fix

Stock synth presets on the Akai MPC are set with a value
that introduces significant vibrato and warble that makes its' otherwise
great synth presets unlistenable. This fix reverse-engineers the bytecode
format via Claude to remove the aftertouch-depth setting to make the 
synths usable. 

## The problem

Every stock preset shipped by AIR is in an unmodified "factory" state
where two settings behave undesirably in practice:

- The MIDI aftertouch-depth parameter is enabled with a nonzero value, 
  (bytes 88-89 and/or 91-92 of the decoded state).
- A related MIDI settings block at bytes 991-999 differs from the value
  AIR's own editor writes once a preset has been touched and resaved.

Opening each preset in the editor and resaving it fixes this, but not
across a library of more than a thousand presets.

## What the fix does

It applies exactly two changes to each preset's decoded state, and
nothing else:

| Bytes   | Written                       | Notes                                                              |
|---------|-------------------------------|--------------------------------------------------------------------|
| 88-89   | `ff ff`                       | Aftertouch Depth (16-bit);                                         |
| 91-92   | `ff ff`                       | Same, second possible offset                                       |
| 991-999 | `ff d6 38 9b ce ff ff ff ff`  | Verified byte-for-byte identical across every known preset pair    |

Some factory presets also ship without a `<preset>` element. When one
is missing, the tool adds one after the `<PLUGIN .../>` tag, with a name
derived from the filename (e.g. `0104-Pianos-Atmospheric Pick.xpl` ->
`Atmospheric Pick`).

### Why so narrow

An earlier, broader heuristic disabled every setting that looked
MIDI-related, and it was rejected. Byte-level analysis across a library
of 1274 factory presets showed that most of the extra positions it
touched hold real, highly variable, preset-specific synthesis parameters
(not disabled toggles), so zeroing them blindly corrupted presets.

## The `.xpl` format

Fabric XL presets are XML files with a single binary blob embedded as:

```
<state>LENGTH.PAYLOAD</state>
```

- `LENGTH` is the exact byte length of the decoded binary state.
- `PAYLOAD` is standard base64 with three quirks:
  1. `/` is replaced with `.` (so `.` means a literal `/`, not "empty").
  2. Trailing `=` padding is stripped entirely; `LENGTH` is used to
     reconstruct it on decode.
  3. When the byte length isn't a multiple of 3, the unused "filler"
     bits of the last base64 character are set to 1, not 0 as in
     standard base64. Re-encoding without accounting for this still
     decodes correctly, but produces a different string than the
     original, which some parsers reject.

The encoder reproduces the original output byte for byte, which was
verified against known Bad/Fixed reference pairs.

## Install

Requires Python 3.9+.

```sh
pip install .
```

## Usage

```sh
fabric-xl-fix SOURCE DESTINATION [--dry-run] [--force]
```

- `SOURCE` is a single `.xpl` file or a directory of presets.
- `DESTINATION` is the output file (if `SOURCE` is a file) or the output
  directory (if `SOURCE` is a directory).
- `--dry-run` reports what would change without writing any files.
- `--force` allows writing into a destination directory that already
  exists and is not empty.

The tool never modifies presets in place. It always writes to a separate
destination, so your original library is never at risk.

macOS AppleDouble sidecar files (`._Foo.xpl`) are skipped. They are not
presets, and they commonly appear after Finder, `cp` or `ditto` copies
onto non-HFS+ volumes such as the exFAT-formatted MPC Content drive.

Examples:

```sh
# Preview the changes for a whole folder
fabric-xl-fix path/to/presets fixed-presets --dry-run

# Fix it into a new folder
fabric-xl-fix path/to/presets fixed-presets

# Fix a single preset
fabric-xl-fix path/to/presets/MyPreset.xpl fixed/MyPreset.xpl
```

The command exits with status 1 if any preset fails to parse.

## Tests

```sh
python -m unittest discover tests
```

## License

See [LICENSE](LICENSE).
