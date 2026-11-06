"""A real, minimal PDF writer for fixtures: no dependency, Helvetica text,
one line per entry. Used by the PDF intake tests and the injection suite."""
from __future__ import annotations

import zlib


def make_pdf(pages: list[list[str]], compress: bool = True, pad_stream: int = 0, encrypt_marker: bool = False,
             declared_size: int | None = None) -> bytes:
    """A real, minimal PDF: one Helvetica text object per page, a line per
    entry. `pad_stream` appends that many spaces to every content stream
    (compressed, a small file that inflates large)."""
    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        body = "BT /F1 10 Tf 14 TL 50 790 Td " + " ".join(f"({esc(ln)}) Tj T*" for ln in lines) + " ET"
        raw = body.encode("latin-1") + b" " * pad_stream
        data = zlib.compress(raw, 9) if compress else raw
        filt = b" /Filter /FlateDecode" if compress else b""
        objs.append(b"<< /Length " + str(len(data)).encode() + filt + b" >>\nstream\n" + data + b"\nendstream")
        content_no = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {content_no} 0 R >>".encode())
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    size = declared_size if declared_size is not None else len(objs) + 1
    trailer = f"trailer\n<< /Size {size} /Root 1 0 R"
    if encrypt_marker:
        trailer += " /Encrypt << /Filter /Standard /V 1 /R 2 /O <00> /U <00> /P -4 >>"
    out += (trailer + f" >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)
