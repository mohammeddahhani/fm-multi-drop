#!/usr/bin/env python3
"""
Static checks on the cave bytes inside a built SLUS (Unicorn can't see these):
  * R3000 load-delay hazards (load result used by the very next instruction)
  * every branch/jump has a nop in its delay slot (cave is written with noreorder)
  * no absolute j/jal into the cave's own range (would break if it moves)
Usage: python tools/static_checks.py PATCHED_SLUS [--size 408]
"""
import argparse, sys
T, H, CAVE = 0x80010000, 0x800, 0x801db038
ap = argparse.ArgumentParser(); ap.add_argument("slus"); ap.add_argument("--size", type=int, default=408)
a = ap.parse_args()
d = open(a.slus, "rb").read()
w = lambda addr: int.from_bytes(d[(addr - T) + H:(addr - T) + H + 4], "little")
LOADS = {32, 33, 34, 35, 36, 37, 38}
problems = []
for addr in range(CAVE + 4, CAVE + a.size, 4):
    x, nx = w(addr), w(addr + 4)
    op, rt = x >> 26, (x >> 16) & 31
    if op in LOADS and nx != 0 and rt != 0:
        nop_, nrs, nrt = nx >> 26, (nx >> 21) & 31, (nx >> 16) & 31
        stores_or_r = nop_ == 0 or nop_ in (4, 5, 40, 41, 43)
        reads = {nrs, nrt} if stores_or_r else {nrs}
        if rt in reads:
            problems.append(f"load-delay hazard at 0x{addr:08x}")
    is_branch = op in (2, 3, 4, 5, 6, 7, 1) or (op == 0 and (x & 63) in (8, 9))
    if is_branch and nx != 0:
        problems.append(f"non-nop delay slot after 0x{addr:08x}")
    if op in (2, 3):
        tgt = ((addr + 4) & 0xF0000000) | ((x & 0x3FFFFFF) << 2)
        if CAVE <= tgt < CAVE + a.size:
            problems.append(f"absolute jump into the cave at 0x{addr:08x} -> 0x{tgt:08x}")
print("static checks:", "FAIL" if problems else "ok (no load-delay hazards, all delay slots nop, no absolute self-jumps)")
for p in problems: print("  ", p)
sys.exit(1 if problems else 0)
