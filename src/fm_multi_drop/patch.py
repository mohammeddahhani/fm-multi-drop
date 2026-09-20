"""The multi-drop patch: detection of the input executable, and applying/reverting the patch.

Nothing here contains game data. The patch is a small MIPS routine ("cave", see
cave_data.py / asm/cave.s) placed in unused padding of SLUS_014.11 plus one hook
that jumps to it. The unmodified executable is recognised by its SHA-256, so the
tool needs no reference copy and refuses executables it does not recognise.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import struct
from typing import Optional

from .cave_data import CAVE


class PatchError(Exception):
    """The executable cannot be patched (unsupported or already modified by something else)."""


@dataclasses.dataclass(frozen=True)
class PatchSpec:
    slus_name: str = "SLUS_014.11"
    slus_size: int = 1902592
    text_addr: int = 0x80010000      # RAM address the file body is loaded at
    header_size: int = 0x800         # PS-EXE header before the loaded body
    vanilla_sha256: str = "375b5f6de0dec0622405755a3c9c3c65953ff7d050090c59546c3ff4f489755b"
    hook_addr: int = 0x80021c68      # `lw $a0, 0x2e0($gp)` right after the reward roll
    hook_vanilla: bytes = bytes.fromhex("e002848f")
    cave_addr: int = 0x801db038      # zero padding between two functions
    cave_region_size: int = 632      # size of that all-zero padding
    cave: bytes = CAVE               # byte 0 is the drop count, patched in

    def offset(self, ram: int) -> int:
        return (ram - self.text_addr) + self.header_size

    @property
    def hook_patched(self) -> bytes:
        loop_entry = self.cave_addr + 4
        return struct.pack("<I", (2 << 26) | ((loop_entry >> 2) & 0x3FFFFFF))  # j loop_entry


DEFAULT = PatchSpec()
MAX_DROPS = 255


class State(enum.Enum):
    VANILLA = "unmodified"
    PATCHED = "already patched by fm-multi-drop"
    FOREIGN = "unsupported"


@dataclasses.dataclass(frozen=True)
class Inspection:
    state: State
    drops: Optional[int]
    detail: str


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def revert(slus: bytes, spec: Optional[PatchSpec] = None) -> bytes:
    spec = spec or DEFAULT
    data = bytearray(slus)
    ho, co = spec.offset(spec.hook_addr), spec.offset(spec.cave_addr)
    data[ho:ho + 4] = spec.hook_vanilla
    data[co:co + spec.cave_region_size] = b"\x00" * spec.cave_region_size
    return bytes(data)


def inspect(slus: bytes, spec: Optional[PatchSpec] = None) -> Inspection:
    spec = spec or DEFAULT
    if len(slus) != spec.slus_size or slus[:8] != b"PS-X EXE":
        return Inspection(State.FOREIGN, None, f"{spec.slus_name} has an unexpected size or header")
    ho, co = spec.offset(spec.hook_addr), spec.offset(spec.cave_addr)
    hook = slus[ho:ho + 4]
    region = slus[co:co + spec.cave_region_size]
    n_cave = len(spec.cave)
    if hook == spec.hook_patched and region[1:n_cave] == spec.cave[1:] and not any(region[n_cave:]):
        if region[0] == 0:
            return Inspection(State.FOREIGN, None, "found this tool's patch with a drop count of 0")
        if _sha(revert(slus, spec)) == spec.vanilla_sha256:
            return Inspection(State.PATCHED, region[0], f"already patched with {region[0]} drops per win")
        return Inspection(State.FOREIGN, None,
                          "this tool's patch is present, but the rest of the executable is modified too")
    if hook == spec.hook_vanilla and not any(region):
        if _sha(slus) == spec.vanilla_sha256:
            return Inspection(State.VANILLA, None, "unmodified US SLUS_014.11")
        return Inspection(State.FOREIGN, None,
                          f"the executable differs from the unmodified US {spec.slus_name} "
                          f"(sha256 {_sha(slus)[:16]}...). Discs with a modified executable, such as the "
                          "Pharaoh (Hard) and GOD modes, are not supported")
    return Inspection(State.FOREIGN, None,
                      "the executable already contains a different multi-drop / code patch "
                      "(hook or padding area is not in the expected state)")


def apply(slus: bytes, drops: int, spec: Optional[PatchSpec] = None) -> bytes:
    spec = spec or DEFAULT
    if not 1 <= drops <= MAX_DROPS:
        raise PatchError(f"drops must be between 1 and {MAX_DROPS}")
    info = inspect(slus, spec)
    if info.state is State.FOREIGN:
        raise PatchError(info.detail)
    base = revert(slus, spec) if info.state is State.PATCHED else slus
    data = bytearray(base)
    cave = bytearray(spec.cave)
    cave[0] = drops
    ho, co = spec.offset(spec.hook_addr), spec.offset(spec.cave_addr)
    data[co:co + len(cave)] = cave
    data[ho:ho + 4] = spec.hook_patched
    return bytes(data)
