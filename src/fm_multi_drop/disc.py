"""Minimal reader/writer for raw 2352-byte/sector CD images (.bin / .iso) with ISO9660."""
from __future__ import annotations

import os
import struct
from typing import Iterator, Optional, Tuple

from .sector import (DATA_OFFSET, DATA_SIZE, SECTOR_SIZE, SYNC, fill_edc_ecc, is_form1_mode2)


class DiscError(Exception):
    """The image is not something this tool can read or modify safely."""


class RawDisc:
    def __init__(self, path: str, writable: bool = False):
        self.path = path
        try:
            self._f = open(path, "r+b" if writable else "rb")
        except OSError as e:
            raise DiscError(f"cannot open {path}: {e.strerror or e}") from e
        self.size = os.fstat(self._f.fileno()).st_size
        if self.size == 0 or self.size % SECTOR_SIZE:
            self.close()
            hint = ""
            if self.size and self.size % DATA_SIZE == 0:
                hint = (" It looks like a 2048-byte/sector ISO; this tool needs a raw "
                        "2352-byte/sector image (usually the .bin next to a .cue).")
            raise DiscError(f"{os.path.basename(path)} is not a raw 2352-byte/sector disc image "
                            f"(size {self.size} is not a multiple of {SECTOR_SIZE}).{hint}")
        self.sectors = self.size // SECTOR_SIZE

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "RawDisc":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def read_sector(self, lba: int) -> bytes:
        if not 0 <= lba < self.sectors:
            raise DiscError(f"sector {lba} is outside the image ({self.sectors} sectors)")
        self._f.seek(lba * SECTOR_SIZE)
        return self._f.read(SECTOR_SIZE)

    def read_data(self, lba: int, count: int) -> bytes:
        out = bytearray()
        for i in range(count):
            s = self.read_sector(lba + i)
            if s[:12] != SYNC:
                raise DiscError(f"sector {lba + i} has no CD sync pattern; not a raw 2352-byte/sector image")
            out += s[DATA_OFFSET:DATA_OFFSET + DATA_SIZE]
        return bytes(out)

    def _root(self) -> Tuple[int, int]:
        pvd = self.read_data(16, 1)
        if pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise DiscError("no ISO9660 volume descriptor at sector 16; not a PlayStation data disc image")
        return struct.unpack_from("<I", pvd, 156 + 2)[0], struct.unpack_from("<I", pvd, 156 + 10)[0]

    def _entries(self, extent: int, size: int) -> Iterator[Tuple[str, int, int, bool]]:
        data = self.read_data(extent, (size + DATA_SIZE - 1) // DATA_SIZE)
        o = 0
        while o < len(data):
            length = data[o]
            if length == 0:
                o = (o // DATA_SIZE + 1) * DATA_SIZE
                continue
            ext = struct.unpack_from("<I", data, o + 2)[0]
            sz = struct.unpack_from("<I", data, o + 10)[0]
            is_dir = bool(data[o + 25] & 2)
            name = data[o + 33:o + 33 + data[o + 32]]
            if name not in (b"\x00", b"\x01"):
                yield name.decode("ascii", "replace").split(";")[0], ext, sz, is_dir
            o += length

    def find_file(self, path: str) -> Optional[Tuple[int, int]]:
        """Return (first sector, size in bytes) of e.g. 'SLUS_014.11' or 'DATA/FILE.BIN'."""
        extent, size = self._root()
        parts = [p for p in path.split("/") if p]
        for i, part in enumerate(parts):
            for name, ext, sz, is_dir in self._entries(extent, size):
                if name.upper() == part.upper():
                    if i == len(parts) - 1:
                        return ext, sz
                    if not is_dir:
                        return None
                    extent, size = ext, sz
                    break
            else:
                return None
        return None

    def overwrite_file_data(self, lba: int, data: bytes) -> list:
        """Replace a file's bytes in place; only sectors whose data changes are rewritten.

        Headers are kept and EDC/ECC are recomputed for the rewritten sectors.
        Returns the sector numbers that were modified.
        """
        modified = []
        for i in range((len(data) + DATA_SIZE - 1) // DATA_SIZE):
            sector = bytearray(self.read_sector(lba + i))
            chunk = data[i * DATA_SIZE:(i + 1) * DATA_SIZE]
            if sector[DATA_OFFSET:DATA_OFFSET + len(chunk)] == chunk:
                continue
            if not is_form1_mode2(bytes(sector)):
                raise DiscError(f"sector {lba + i} is not a Mode 2 Form 1 data sector; refusing to modify it")
            sector[DATA_OFFSET:DATA_OFFSET + len(chunk)] = chunk
            fill_edc_ecc(sector)
            self._f.seek((lba + i) * SECTOR_SIZE)
            self._f.write(sector)
            modified.append(lba + i)
        self._f.flush()
        return modified
