#!/usr/bin/env python3
"""Maintainers: extract SLUS_014.11 from a disc image you own (for emulator_check.py).

Usage: python tools/extract_slus.py DISC.iso OUT_SLUS   (run from the repo root)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from fm_multi_drop.cli import read_slus  # noqa: E402
from fm_multi_drop.disc import RawDisc  # noqa: E402

if len(sys.argv) != 3:
    sys.exit(__doc__)
with RawDisc(sys.argv[1]) as disc:
    lba, slus = read_slus(disc)
open(sys.argv[2], "wb").write(slus)
print(f"wrote {sys.argv[2]} ({len(slus)} bytes, from sector {lba})")
