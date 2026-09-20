"""Command line interface: fm-multi-drop INPUT.iso --drops N [-o OUTPUT.iso]"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from typing import Optional, Sequence

from . import __version__
from .cave_data import CAVE_SHA256
from .disc import DiscError, RawDisc
from . import patch as _patch
from .patch import MAX_DROPS, PatchError, State, apply, inspect
from .sector import DATA_SIZE, SECTOR_SIZE, check_sector, fill_edc_ecc

MIN_PYTHON = (3, 9)
CHUNK = 8 * 1024 * 1024


class ToolError(Exception):
    pass


def _log(msg: str = "") -> None:
    print(msg, flush=True)


def read_slus(disc: RawDisc):
    spec = _patch.DEFAULT
    loc = disc.find_file(spec.slus_name)
    if loc is None:
        raise DiscError(f"{spec.slus_name} was not found on the disc. This tool supports the US release "
                        "of Yu-Gi-Oh! Forbidden Memories (SLUS_014.11) and mods of it.")
    lba, size = loc
    if size != spec.slus_size:
        raise DiscError(f"{spec.slus_name} has an unexpected size ({size} bytes, expected {spec.slus_size})")
    return lba, disc.read_data(lba, (size + DATA_SIZE - 1) // DATA_SIZE)[:size]


def default_output(path: str, drops: int) -> str:
    base, ext = os.path.splitext(path)
    base = re.sub(r"\.\d+drops$", "", base)
    return f"{base}.{drops}drops{ext or '.iso'}"


def _copy(src: str, dst: str, total: int) -> None:
    done, last = 0, -1
    tty = sys.stderr.isatty()
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            chunk = fi.read(CHUNK)
            if not chunk:
                break
            fo.write(chunk)
            done += len(chunk)
            pct = done * 100 // total
            step = pct if tty else pct // 25 * 25
            if step != last:
                last = step
                end = "\r" if tty else "\n"
                print(f"  copying... {pct:3d}%", end=end, file=sys.stderr, flush=True)
    if tty:
        print(file=sys.stderr)


def _verify(src: str, out: str, lba: int, drops: int, modified: list) -> None:
    """Re-read the finished image: correct patch, valid sectors, and nothing else changed."""
    with RawDisc(out) as disc:
        _, slus = read_slus(disc)
        info = inspect(slus)
        if info.state is not State.PATCHED or info.drops != drops:
            raise ToolError(f"verification failed: patched executable not recognised ({info.detail})")
        for s in modified:
            edc_ok, ecc_ok = check_sector(disc.read_sector(s))
            if not (edc_ok and ecc_ok):
                raise ToolError(f"verification failed: sector {s} has a bad checksum")
    changed = set()
    with open(src, "rb") as a, open(out, "rb") as b:
        pos = 0
        while True:
            x, y = a.read(CHUNK), b.read(CHUNK)
            if x != y:
                for off in range(0, max(len(x), len(y)), SECTOR_SIZE):
                    if x[off:off + SECTOR_SIZE] != y[off:off + SECTOR_SIZE]:
                        changed.add((pos + off) // SECTOR_SIZE)
            if not x and not y:
                break
            pos += len(x)
    if changed != set(modified):
        raise ToolError(f"verification failed: changed sectors {sorted(changed)} differ from the "
                        f"intended {sorted(modified)}")


def self_test() -> int:
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, found {sys.version.split()[0]}")
    if hashlib.sha256(_patch.DEFAULT.cave).hexdigest() != CAVE_SHA256:
        problems.append("embedded patch code does not match its recorded checksum")
    if _patch.DEFAULT.hook_patched != bytes.fromhex("0f6c0708"):
        problems.append("hook encoding is not the expected `j 0x801db03c`")
    if len(_patch.DEFAULT.cave) > _patch.DEFAULT.cave_region_size:
        problems.append("patch code does not fit the padding area")
    s = bytearray(SECTOR_SIZE)
    s[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    s[15] = 2
    fill_edc_ecc(s)
    if check_sector(bytes(s)) != (True, True):
        problems.append("sector checksum self-check failed")
    if problems:
        for p in problems:
            print(f"self-test FAILED: {p}", file=sys.stderr)
        return 1
    _log(f"self-test ok (fm-multi-drop {__version__}, Python {sys.version.split()[0]})")
    return 0


def _run(a: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if a.self_test:
        return self_test()
    if not a.input:
        parser.error("the input disc image is required (see --help)")
    if not a.check:
        if a.drops is None:
            parser.error("--drops N is required (how many cards you get per duel win)")
        if not 1 <= a.drops <= MAX_DROPS:
            parser.error(f"--drops must be between 1 and {MAX_DROPS}")
    if not os.path.isfile(a.input):
        raise ToolError(f"input file not found: {a.input}")

    with RawDisc(a.input) as disc:
        lba, slus = read_slus(disc)
    info = inspect(slus)
    _log(f"Disc:  {os.path.basename(a.input)}  ({os.path.getsize(a.input) / 1e6:.0f} MB)")
    if info.state is State.FOREIGN:
        _log(f"Game:  {_patch.DEFAULT.slus_name} found at sector {lba}")
        raise ToolError(info.detail)
    _log(f"Game:  {_patch.DEFAULT.slus_name} at sector {lba}: {info.detail}")
    if a.check:
        _log("OK: this disc can be patched.")
        return 0

    out = a.output or default_output(a.input, a.drops)
    if os.path.abspath(out) == os.path.abspath(a.input) or (
            os.path.exists(out) and os.path.samefile(out, a.input)):
        raise ToolError("the output must be a different file than the input (the input is never modified)")
    if os.path.exists(out) and not a.force:
        raise ToolError(f"{out} already exists (use --force to overwrite)")
    size = os.path.getsize(a.input)
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free
    if free < size + 64 * 1024 * 1024:
        raise ToolError(f"not enough free disk space for the output ({size / 1e6:.0f} MB needed, "
                        f"{free / 1e6:.0f} MB free)")

    patched = apply(slus, a.drops)
    partial = out + ".partial"
    try:
        _log(f"Writing {out} ...")
        _copy(a.input, partial, size)
        with RawDisc(partial, writable=True) as disc:
            modified = disc.overwrite_file_data(lba, patched)
        _log(f"Verifying ... (rewrote {len(modified)} of the disc's {size // SECTOR_SIZE} sectors)")
        _verify(a.input, partial, lba, a.drops, modified)
        os.replace(partial, out)
    except BaseException:
        if os.path.exists(partial):
            os.remove(partial)
        raise
    _log(f"Done: {out}")
    _log(f"You now get {a.drops} card(s) per duel win. Your original disc was not modified.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fm-multi-drop",
        description="Patch a Yu-Gi-Oh! Forbidden Memories (US) disc image so a duel win gives N cards "
                    "instead of 1. Works on the normal Kuriboh mod and the stock game. "
                    "Your input file is never modified; a new image is written.",
        epilog="Example: fm-multi-drop \"YFM MOD KURIBOH.iso\" --drops 10")
    p.add_argument("input", nargs="?", help="raw 2352-byte/sector disc image (.iso/.bin) that you own")
    p.add_argument("-n", "--drops", type=int, metavar="N",
                   help=f"cards per duel win, 1-{MAX_DROPS} (this includes the game's normal drop)")
    p.add_argument("-o", "--output", help="output image (default: <input>.<N>drops.<ext> next to the input)")
    p.add_argument("-f", "--force", action="store_true", help="overwrite the output if it exists")
    p.add_argument("--check", action="store_true", help="only check whether the disc can be patched")
    p.add_argument("--self-test", action="store_true", help="check the installation and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    if sys.version_info < MIN_PYTHON:
        print(f"error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required "
              f"(you have {sys.version.split()[0]}). Get it from https://www.python.org/downloads/",
              file=sys.stderr)
        return 1
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args, parser)
    except (ToolError, DiscError, PatchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted; no output file was left behind", file=sys.stderr)
        return 130
