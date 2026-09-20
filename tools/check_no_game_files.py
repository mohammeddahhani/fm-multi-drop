#!/usr/bin/env python3
"""Fail if the repository contains anything that looks like game data, a disc image,
a save file or a BIOS. Used by the tests and by the local pre-commit hook.

Usage: python tools/check_no_game_files.py [--staged]
  default   checks every file git would add (tracked or untracked, minus .gitignore)
  --staged  checks only what is staged for commit
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_EXT = {".iso", ".bin", ".cue", ".img", ".mdf", ".mds", ".ccd", ".sub", ".chd", ".pbp",
                 ".mcd", ".mcr", ".mc", ".srm", ".sav", ".psv", ".vmp", ".mrg", ".exe", ".zip",
                 ".rar", ".7z", ".dll", ".so"}
TEXT_EXT = {".py", ".md", ".sh", ".bat", ".toml", ".txt", ".s", ".ld", ".yml", ".yaml", ".cfg", ".ini", ""}
NAME_RE = re.compile(r"(slus|scus|sles|sces|slps)_\d|scph|bios|wa_mrg", re.I)
MAGICS = {b"PS-X EXE": "PlayStation executable header",
          b"\x00" + b"\xff" * 10 + b"\x00": "raw CD sector sync pattern",
          b"CD001": "ISO9660 volume descriptor"}
MAX_TEXT = 300_000
MAX_ANY = 1_000_000
ALLOWED_NAMES = {"LICENSE", "README.md", ".gitignore"}


def candidates(staged=False):
    try:
        if staged:
            cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
        else:
            cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "venv", "__pycache__", "build", "dist"}
        found = []
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in skip and not x.endswith(".egg-info")]
            found += [os.path.relpath(os.path.join(d, f), ROOT) for f in files]
        return found


def scan(rel_paths, root=ROOT):
    problems = []
    for rel in rel_paths:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        base, ext = os.path.basename(rel), os.path.splitext(rel)[1].lower()
        size = os.path.getsize(path)
        if ext in FORBIDDEN_EXT:
            problems.append(f"{rel}: forbidden file type {ext}")
        if NAME_RE.search(base) and base not in ALLOWED_NAMES and not rel.endswith((".md", ".py", ".sh", ".bat")):
            problems.append(f"{rel}: name looks like game/BIOS data")
        if size > MAX_ANY or (ext in TEXT_EXT and size > MAX_TEXT):
            problems.append(f"{rel}: unexpectedly large ({size} bytes)")
            continue
        if ext in TEXT_EXT and ext != "":
            with open(path, "rb") as f:
                if b"\x00" in f.read(4096):
                    problems.append(f"{rel}: text file contains binary data")
            continue
        with open(path, "rb") as f:
            data = f.read()
        for magic, what in MAGICS.items():
            if magic in data:
                problems.append(f"{rel}: contains a {what}")
    return problems


def main(argv):
    problems = scan(candidates("--staged" in argv))
    if problems:
        print("REFUSING: possible game data / disc image / BIOS in the repository:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("no game data, disc images, saves or BIOS files found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
