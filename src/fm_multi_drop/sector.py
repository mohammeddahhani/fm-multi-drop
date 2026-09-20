"""CD-ROM XA Mode 2 Form 1 sector helpers: EDC checksum and ECC (P/Q parity).

A raw sector is 2352 bytes: sync(12) header(4) subheader(8) data(2048) EDC(4)
ECC-P(172) ECC-Q(104). Only the 2048 data bytes are user content; when they change
the EDC and ECC must be recomputed for the sector to stay valid.
"""
from __future__ import annotations

SECTOR_SIZE = 2352
DATA_OFFSET = 24
DATA_SIZE = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
EDC_OFFSET = 2072
ECC_P_OFFSET = 2076  # 172 bytes
ECC_Q_OFFSET = 2248  # 104 bytes


def _build_tables():
    edc = []
    for i in range(256):
        e = i
        for _ in range(8):
            e = (e >> 1) ^ 0xD8018001 if e & 1 else e >> 1
        edc.append(e & 0xFFFFFFFF)
    fwd = [0] * 256
    back = [0] * 256
    for i in range(256):
        j = (i << 1) ^ (0x11D if i & 0x80 else 0)
        fwd[i] = j
        back[i ^ j] = i
    return edc, fwd, back


_EDC, _F, _B = _build_tables()


def compute_edc(data: bytes) -> int:
    edc = 0
    for b in data:
        edc = _EDC[(edc ^ b) & 0xFF] ^ (edc >> 8)
    return edc & 0xFFFFFFFF


def _ecc_block(src: bytes, major_count: int, minor_count: int, major_mult: int, minor_inc: int) -> bytes:
    size = major_count * minor_count
    first = bytearray(major_count)
    second = bytearray(major_count)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        first[major] = a
        second[major] = a ^ b
    return bytes(first) + bytes(second)


def compute_ecc(sector: bytes) -> bytes:
    """Return the 276 ECC bytes (P then Q) for a Mode 2 Form 1 sector.

    The 4 header address bytes are treated as zero, as the CD-ROM XA spec requires.
    Expects the sector's EDC (bytes 2072..2075) to already be correct.
    """
    src = bytearray(sector[12:12 + 2236])
    src[0:4] = b"\x00\x00\x00\x00"
    p = _ecc_block(bytes(src[:2064]), 86, 24, 2, 86)
    src[2064:2064 + 172] = p  # Q parity covers P parity
    q = _ecc_block(bytes(src), 52, 43, 86, 88)
    return p + q


def fill_edc_ecc(sector: bytearray) -> None:
    edc = compute_edc(bytes(sector[16:2072]))
    sector[EDC_OFFSET:EDC_OFFSET + 4] = edc.to_bytes(4, "little")
    sector[ECC_P_OFFSET:SECTOR_SIZE] = compute_ecc(bytes(sector))


def check_sector(sector: bytes) -> tuple[bool, bool]:
    """(edc_ok, ecc_ok) for a Mode 2 Form 1 sector."""
    edc_ok = int.from_bytes(sector[EDC_OFFSET:EDC_OFFSET + 4], "little") == compute_edc(bytes(sector[16:2072]))
    ecc_ok = sector[ECC_P_OFFSET:SECTOR_SIZE] == compute_ecc(sector)
    return edc_ok, ecc_ok


def is_form1_mode2(sector: bytes) -> bool:
    return (sector[0:12] == SYNC and sector[15] == 2 and sector[18] & 0x20 == 0
            and sector[16:20] == sector[20:24])
