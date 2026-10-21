"""Command-line interface for fabric-xl-fix.

Always writes to a separate destination rather than modifying presets
in place, so the original library is never at risk.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import PresetFormatError, fix_preset_text, guess_preset_name

__version__ = "1.0.0"


def _iter_xpl_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    # Skip macOS AppleDouble sidecar files (._Foo.xpl), which are not
    # presets and commonly appear after Finder/cp/ditto copies onto
    # non-HFS+ volumes such as the exFAT-formatted MPC Content drive.
    return sorted(p for p in path.glob("*.xpl") if not p.name.startswith("._"))


def _copy_file(src: Path, dst: Path) -> None:
    dst.write_bytes(src.read_bytes())


def fix_one(src: Path, dst: Path) -> tuple[bool, str]:
    try:
        text = src.read_text(encoding="utf-8", errors="ignore")
        result = fix_preset_text(text, preset_name_hint=guess_preset_name(src.name))
    except PresetFormatError as e:
        return False, str(e)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="") as f:
        f.write(result.text)
    return True, "changed" if result.changed else "already fixed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fabric-xl-fix",
        description=(
            "Fix the MIDI aftertouch-depth and settings-block issue in AIR "
            "Fabric XL presets (.xpl files)."
        ),
    )
    parser.add_argument("source", type=Path, help="a single .xpl file, or a directory of presets")
    parser.add_argument(
        "destination",
        type=Path,
        help="output file (if source is a file) or output directory (if source is a directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow writing into a destination directory that already exists and is non-empty",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing any files",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.error(f"source not found: {args.source}")

    if args.source.is_dir() and args.destination.exists() and not args.force:
        if any(args.destination.iterdir()):
            parser.error(
                f"destination {args.destination} already exists and is non-empty "
                "(use --force to write into it anyway)"
            )

    files = _iter_xpl_files(args.source)
    if not files:
        parser.error(f"no .xpl files found in {args.source}")

    fixed = changed = failed = 0
    for src_file in files:
        if args.source.is_dir():
            dst_file = args.destination / src_file.name
        else:
            dst_file = args.destination

        if args.dry_run:
            try:
                text = src_file.read_text(encoding="utf-8", errors="ignore")
                result = fix_preset_text(text, preset_name_hint=guess_preset_name(src_file.name))
                fixed += 1
                changed += result.changed
                print(f"{'would change' if result.changed else 'no change needed':17s} {src_file.name}")
            except PresetFormatError as e:
                failed += 1
                print(f"{'SKIP (' + str(e) + ')':17s} {src_file.name}", file=sys.stderr)
            continue

        ok, status = fix_one(src_file, dst_file)
        if ok:
            fixed += 1
            changed += status == "changed"
        else:
            failed += 1
            print(f"FAILED: {src_file.name}: {status}", file=sys.stderr)

    verb = "Would fix" if args.dry_run else "Fixed"
    print(f"\n{verb} {fixed}/{len(files)} presets ({changed} needed changes, {failed} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
