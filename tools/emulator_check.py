#!/usr/bin/env python3
"""
Differential test: after the Hook 1 cave runs, the CPU state at the resume point
(0x80021c70) must equal what unpatched vanilla has there. Runs both from the hook
site (0x80021c68) over many randomized machine states and compares all 32 GPRs
+ HI/LO. Also reports which memory the patched run wrote.

Fails (exit 1) on any register mismatch, any GrantCard call with an invalid card
id, or any write into the deck array (the v7 clamp-to-0 flaw trips the last two).

Needs `unicorn` (pip install unicorn, e.g. in a venv). NOTE: Unicorn's MIPS32
core has no R3000 load-delay slot, so load-delay hazards are NOT covered here --
check those statically (see tools/static_checks.py).

Usage: python tools/emulator_check.py PATCHED_SLUS --vanilla VANILLA_SLUS [--runs 300] [--seed 1]

Both files are your own: extract them with tools/extract_slus.py (the vanilla one from a disc
whose executable is unmodified, the patched one from the tool's output). Nothing here ships game data.
"""
import argparse, os, random, sys
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.mips_const import *

T, H = 0x80010000, 0x800
HOOK, RESUME, CAVE = 0x80021c68, 0x80021c70, 0x801db038
GRANT = 0x80021894
DECK_LO, DECK_HI = 0x1d0200, 0x1d0250
NAMES = ["zero","at","v0","v1","a0","a1","a2","a3","t0","t1","t2","t3","t4","t5","t6","t7",
         "s0","s1","s2","s3","s4","s5","s6","s7","t8","t9","k0","k1","gp","sp","fp","ra"]
REG = [getattr(sys.modules[__name__], f"UC_MIPS_REG_{i}") for i in range(32)]
RAM = 0x200000
ph = lambda a: a & 0x1FFFFFFF


def make_emu(image, gp0):
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, RAM)
    uc.mem_write(ph(T), image[H:])
    return uc


def setup(uc, rnd, gp0, n):
    w32 = lambda a, v: uc.mem_write(ph(a), (v & 0xFFFFFFFF).to_bytes(4, "little"))
    struct_addr = 0x801e8000
    w32(gp0 + 0x2e0, struct_addr)
    uc.mem_write(ph(struct_addr) + 0x38, bytes([rnd.randint(0, 5), rnd.randint(0, 1)]))
    for cat in range(3):
        counts = [0] * 722
        for _ in range(2048):
            counts[rnd.randrange(722)] += 1
        if rnd.random() < 0.15:
            counts = [rnd.randrange(0, 40) for _ in range(722)]
        uc.mem_write(ph(0x8017878C + cat * 1460), b"".join(c.to_bytes(2, "little") for c in counts))
    uc.mem_write(ph(0x8009b361), bytes([rnd.randrange(0, 128)]))
    uc.mem_write(ph(0x801cf310), bytes([rnd.choice([0, 0, 0, 1, 2, 5, 0xFF, 0xFD])]))
    uc.mem_write(ph(0x801d06f4), bytes(rnd.randrange(256) for _ in range(16)))
    w32(0x800fe6f8, rnd.getrandbits(32))
    uc.mem_write(ph(CAVE), bytes([n]))


def init_regs(uc, rnd, gp0):
    st = {}
    for i in range(1, 32):
        st[i] = rnd.getrandbits(32)
    st[28] = gp0
    st[29] = 0x801fff00 - 8 * rnd.randint(0, 64)
    st[16] = rnd.choice([0, rnd.getrandbits(32)])
    for i, v in st.items():
        uc.reg_write(REG[i], v)
    hi, lo = rnd.getrandbits(32), rnd.getrandbits(32)
    uc.reg_write(UC_MIPS_REG_HI, hi); uc.reg_write(UC_MIPS_REG_LO, lo)
    return st, hi, lo


def snapshot(uc):
    return [uc.reg_read(REG[i]) for i in range(32)] + [uc.reg_read(UC_MIPS_REG_HI), uc.reg_read(UC_MIPS_REG_LO)]


def run_once(image, seed, gp0, n):
    uc = make_emu(image, gp0)
    rnd = random.Random(seed)
    setup(uc, rnd, gp0, n)
    st, hi, lo = init_regs(uc, rnd, gp0)
    writes, grants, bad_grants = [], [0], []
    uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, t, a, s, v, d: writes.append((a, s)))

    def on_code(u, a, s, d):
        if a == GRANT:
            grants[0] += 1
            card = u.reg_read(UC_MIPS_REG_4)
            if not 1 <= card <= 722:
                bad_grants.append(card)
    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.emu_start(HOOK, RESUME, count=2_000_000)
    return snapshot(uc), writes, grants[0], st[29], bad_grants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patched")
    ap.add_argument("--vanilla", required=True, help="unmodified SLUS_014.11 to compare against")
    ap.add_argument("--runs", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    van = open(a.vanilla, "rb").read()
    pat = open(a.patched, "rb").read()
    gp0 = int.from_bytes(van[0x14:0x18], "little")
    bad = {}
    outside = {}
    total_grants = 0
    bad_grant_vals = []
    deck_writes = 0
    for k in range(a.runs):
        seed = a.seed * 100000 + k
        n = random.Random(seed ^ 0x55).randint(1, 12)
        exp = run_once(van, seed, gp0, n)[0]
        act, writes, grants, sp0, bad_grants = run_once(pat, seed, gp0, n)
        total_grants += grants
        bad_grant_vals += bad_grants
        for i, (e, x) in enumerate(zip(exp, act)):
            if e != x:
                nm = NAMES[i] if i < 32 else ("hi" if i == 32 else "lo")
                bad[nm] = bad.get(nm, 0) + 1
        for addr, size in writes:
            if DECK_LO <= ph(addr) < DECK_HI:
                deck_writes += 1
            if not (sp0 - 0x1000 <= addr < sp0):
                region = addr & ~0xFF
                outside[region] = outside.get(region, 0) + 1
    print(f"{a.patched}: {a.runs} randomized runs, {total_grants} GrantCard calls")
    if bad:
        print("REGISTER MISMATCHES vs vanilla at resume point (register: runs differing):")
        for k, v in sorted(bad.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
    else:
        print("all 32 GPRs + HI/LO identical to vanilla at the resume point in every run")
    print(f"GrantCard calls with an invalid card id (not 1..722): {len(bad_grant_vals)}"
          + (f" (values {sorted(set(bad_grant_vals))[:8]})" if bad_grant_vals else ""))
    print(f"writes into the deck array 0x801d0200-0x801d024f: {deck_writes}")
    print("non-stack write regions (256B blocks):", ", ".join(f"0x{r:08x}" for r in sorted(outside)))
    sys.exit(1 if (bad or bad_grant_vals or deck_writes) else 0)


if __name__ == "__main__":
    main()
