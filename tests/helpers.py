"""Synthetic disc images for the tests: no real game data is involved."""
import dataclasses
import hashlib
import random
import struct

from fm_multi_drop import patch as P
from fm_multi_drop.sector import SYNC, fill_edc_ecc

SLUS_LBA = 25
TOTAL_SECTORS = SLUS_LBA + 929 + 8


def make_slus(spec=None) -> bytes:
    spec = spec or P.DEFAULT
    data = bytearray(random.Random(1234).randbytes(spec.slus_size))
    data[0:8] = b"PS-X EXE"
    ho, co = spec.offset(spec.hook_addr), spec.offset(spec.cave_addr)
    data[ho:ho + 4] = spec.hook_vanilla
    data[co:co + spec.cave_region_size] = bytes(spec.cave_region_size)
    return bytes(data)


def spec_for(slus: bytes) -> "P.PatchSpec":
    return dataclasses.replace(P.DEFAULT, vanilla_sha256=hashlib.sha256(slus).hexdigest())


def sector(lba: int, data: bytes = b"", submode: int = 0x08) -> bytes:
    s = bytearray(2352)
    s[0:12] = SYNC
    bcd = lambda v: ((v // 10) << 4) | (v % 10)
    f = lba + 150
    s[12:16] = bytes([bcd(f // 75 // 60), bcd(f // 75 % 60), bcd(f % 75), 2])
    s[16:24] = bytes([0, 0, submode, 0]) * 2
    s[24:24 + len(data)] = data
    fill_edc_ecc(s)
    return bytes(s)


def dir_record(name: bytes, extent: int, size: int, is_dir: bool) -> bytes:
    length = 33 + len(name)
    length += length % 2
    r = bytearray(length)
    r[0] = length
    struct.pack_into("<I", r, 2, extent)
    struct.pack_into(">I", r, 6, extent)
    struct.pack_into("<I", r, 10, size)
    struct.pack_into(">I", r, 14, size)
    r[25] = 2 if is_dir else 0
    r[32] = len(name)
    r[33:33 + len(name)] = name
    return bytes(r)


def build_disc(path: str, slus: bytes) -> None:
    root_ext, data_ext, file_lba = 20, 21, 60
    pvd = bytearray(2048)
    pvd[0], pvd[1:6], pvd[6] = 1, b"CD001", 1
    pvd[156:190] = dir_record(b"\x00", root_ext, 2048, True)
    root = b"".join([dir_record(b"\x00", root_ext, 2048, True), dir_record(b"\x01", root_ext, 2048, True),
                     dir_record(b"SLUS_014.11;1", SLUS_LBA, len(slus), False),
                     dir_record(b"DATA", data_ext, 2048, True)])
    data = b"".join([dir_record(b"\x00", data_ext, 2048, True), dir_record(b"\x01", root_ext, 2048, True),
                     dir_record(b"FILE.BIN;1", file_lba, 10, False)])
    special = {16: bytes(pvd), root_ext: root, data_ext: data, file_lba: b"0123456789"}
    for i in range(0, len(slus), 2048):
        special[SLUS_LBA + i // 2048] = slus[i:i + 2048]
    with open(path, "wb") as f:
        for lba in range(TOTAL_SECTORS):
            f.write(sector(lba, special.get(lba, b"")))


def differing_sectors(a_path: str, b_path: str) -> set:
    out = set()
    with open(a_path, "rb") as a, open(b_path, "rb") as b:
        lba = 0
        while True:
            x, y = a.read(2352), b.read(2352)
            if not x and not y:
                return out
            if x != y:
                out.add(lba)
            lba += 1


def write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
