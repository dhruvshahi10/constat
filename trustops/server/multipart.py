"""Minimal multipart/form-data parser for http.server.

Hand-rolled on purpose: cgi was removed in Python 3.13 and email.parser
mangles binary payloads unless coaxed. This handles exactly what our upload
form sends — text fields plus one file part — deterministically.
"""
from __future__ import annotations

import re

_DISP = re.compile(
    rb'Content-Disposition:\s*form-data;\s*name="([^"]*)"(?:;\s*filename="([^"]*)")?',
    re.I,
)


class MultipartError(ValueError):
    pass


def parse(body: bytes, content_type: str) -> dict[str, tuple[str | None, bytes]]:
    """Returns {field_name: (filename | None, raw_bytes)}."""
    m = re.search(r'boundary="?([^";]+)"?', content_type)
    if not m:
        raise MultipartError("missing multipart boundary")
    boundary = b"--" + m.group(1).encode()

    parts: dict[str, tuple[str | None, bytes]] = {}
    # split on boundary; first chunk is preamble, last is the "--\r\n" epilogue
    for chunk in body.split(boundary)[1:]:
        if chunk in (b"--", b"--\r\n") or chunk.startswith(b"--"):
            break
        chunk = chunk.lstrip(b"\r\n")
        sep = chunk.find(b"\r\n\r\n")
        if sep < 0:
            raise MultipartError("malformed part: no header terminator")
        headers, payload = chunk[:sep], chunk[sep + 4:]
        # strip the trailing CRLF that precedes the next boundary
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        d = _DISP.search(headers)
        if not d:
            continue
        name = d.group(1).decode("utf-8", "replace")
        filename = d.group(2).decode("utf-8", "replace") if d.group(2) is not None else None
        parts[name] = (filename, payload)
    if not parts:
        raise MultipartError("no form parts found")
    return parts


def text_field(parts: dict, name: str, default: str = "") -> str:
    if name not in parts:
        return default
    return parts[name][1].decode("utf-8", "replace").strip()
