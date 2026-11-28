"""Windows DPAPI storage for the local desktop testing bundle."""

import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
from tempfile import NamedTemporaryFile


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    source = ctypes.create_string_buffer(data)
    incoming = DataBlob(len(data), ctypes.addressof(source))
    outgoing = DataBlob()
    crypt = ctypes.windll.crypt32
    operation = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    if not operation(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError()
    free = ctypes.windll.kernel32.LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free(outgoing.data)


def read_keys(path: Path) -> dict:
    try:
        return json.loads(_dpapi(path.read_bytes(), protect=False))
    except (OSError, ValueError):
        return {}


def remember_keys(path: Path, request: dict) -> None:
    updates = {field: request[field] for field in ("amap_key", "deepseek_key")
               if isinstance(request.get(field), str) and request[field].strip()}
    if not updates:
        return
    existing = read_keys(path)
    if all(existing.get(field) == value for field, value in updates.items()):
        return
    existing.update(updates)
    protected = _dpapi(json.dumps(existing).encode(), protect=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        file.write(protected)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.stdout.write(json.dumps(read_keys(Path(sys.argv[1]))))
