"""Local PDF text worker. No PDF actions, scripts, attachments or URLs are executed."""

import logging
import os
import subprocess
import sys
from io import BytesIO

from pydantic import BaseModel, ConfigDict, Field

MAX_BYTES = 8 * 1024 * 1024


class ExtractedPDF(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pages: int = Field(ge=1, le=10)
    text: str = Field(max_length=4000)
    truncated: bool


def extract_pdf(raw: bytes) -> ExtractedPDF:
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_BYTES:
        raise ValueError("Choose an unencrypted PDF of at most 8 MiB and 10 pages")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment.update(
        PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"
    )
    result = subprocess.run(
        [sys.executable, "-m", "lifegather.documents.extractor"],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=8,
        env=environment,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if len(result.stdout) > 32768:
        raise ValueError("PDF text exceeded limit")
    return ExtractedPDF.model_validate_json(result.stdout)


def worker() -> None:
    logging.disable(logging.CRITICAL)
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    import pypdf.filters as filters
    from pypdf import PdfReader

    filters.ZLIB_MAX_OUTPUT_LENGTH = 2 * 1024 * 1024
    filters.LZW_MAX_OUTPUT_LENGTH = 2 * 1024 * 1024
    filters.RUN_LENGTH_MAX_OUTPUT_LENGTH = 2 * 1024 * 1024
    filters.JBIG2_MAX_OUTPUT_LENGTH = 2 * 1024 * 1024
    filters.JBIG2DEC_BINARY = None
    for name in (
        "MAX_DECLARED_STREAM_LENGTH",
        "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
        "ZLIB_MAX_RECOVERY_INPUT_LENGTH",
    ):
        if hasattr(filters, name):
            setattr(filters, name, 2 * 1024 * 1024)
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or not raw.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF")
    reader = PdfReader(BytesIO(raw), strict=True, root_object_recovery_limit=1000)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
        raise ValueError("Unsupported PDF")
    text = ""
    truncated = False
    for index, page in enumerate(reader.pages):
        contents = page.get_contents()
        if contents and len(contents.get_data()) > 2 * 1024 * 1024:
            raise ValueError("Page content exceeded limit")
        text += ("\n\n" if text else "") + (page.extract_text() or "")
        if len(text) > 4000:
            text = text[:4000]
            truncated = True
            break
        if len(text) == 4000 and index < len(reader.pages) - 1:
            truncated = True
            break
    result = ExtractedPDF(pages=len(reader.pages), text=text, truncated=truncated)
    sys.stdout.buffer.write(result.model_dump_json().encode())


if __name__ == "__main__":
    try:
        worker()
    except Exception:
        sys.exit(1)
