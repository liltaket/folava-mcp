"""Bounded local text extraction; attachment retrieval keeps its existing policy."""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
import shutil
import tempfile
from pathlib import Path

from .client import CanvasError

PDF_TIMEOUT = 15.0
PDF_OUTPUT_LIMIT = 400_000


async def _run(command: str, *args: str, limit: int) -> bytes:
    executable = shutil.which(command)
    if executable is None:
        raise CanvasError(
            "pdf_dependency",
            "PDF text extraction requires Poppler (pdfinfo and pdftotext) on the server machine.",
        )
    try:
        process = await asyncio.create_subprocess_exec(
            executable, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
    except OSError:
        raise CanvasError("pdf_dependency", "Could not start the Poppler PDF tools.") from None
    try:
        async with asyncio.timeout(PDF_TIMEOUT):
            output = await process.stdout.read(limit + 1)
            # StreamReader.read may return a short chunk before EOF.
            while len(output) <= limit:
                chunk = await process.stdout.read(min(65536, limit + 1 - len(output)))
                if not chunk:
                    break
                output += chunk
            if len(output) > limit:
                raise CanvasError("too_large", "PDF extraction exceeds the text output limit.")
            if await process.wait() != 0:
                raise CanvasError(
                    "pdf_unreadable", "PDF could not be read; it may be damaged or encrypted."
                )
            return output
    except TimeoutError:
        raise CanvasError("timeout", "PDF extraction exceeded its time limit.") from None
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        # A full stdout pipe can keep wait() pending after termination.
        # Drain pending pipe data after the producer has stopped.
        await process.communicate()


async def file_text(
    attachment: dict, *, start_page: int = 1, max_pages: int = 10, max_chars: int = 20_000
) -> dict:
    """Extract text without returning binary payloads or signed storage URLs."""
    result = {
        key: value for key, value in attachment.items() if key not in ("content_base64", "text")
    }
    if isinstance(attachment.get("text"), str):
        if start_page != 1:
            raise CanvasError("input", "start_page only applies to PDF attachments.")
        text = attachment["text"]
        result.update(text=text[:max_chars], complete=len(text) <= max_chars)
        if len(text) > max_chars:
            result["content_truncated"] = True
        return result

    mime = attachment.get("mime_type", "").lower()
    if mime != "application/pdf":
        raise CanvasError("unsupported_media", "Text extraction supports UTF-8 text and PDF files.")
    try:
        body = base64.b64decode(attachment["content_base64"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise CanvasError("upstream", "Attachment has an invalid binary payload.") from None
    if not body.startswith(b"%PDF-"):
        raise CanvasError("pdf_unreadable", "Attachment is not a recognizable PDF document.")

    # Local private files only; never pass an upstream filename/URL to Poppler.
    with tempfile.TemporaryDirectory(prefix="folava-pdf-") as directory:
        path = Path(directory) / "document.pdf"
        path.write_bytes(body)
        info = await _run("pdfinfo", str(path), limit=32_000)
        count = re.search(rb"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
        if count is None:
            raise CanvasError("pdf_unreadable", "PDF did not report a page count.")
        total = int(count[1])
        if start_page > total:
            raise CanvasError("input", "start_page exceeds the PDF page count.")
        end = min(total, start_page + max_pages - 1)
        raw = await _run(
            "pdftotext",
            "-f",
            str(start_page),
            "-l",
            str(end),
            "-enc",
            "UTF-8",
            "-q",
            str(path),
            "-",
            limit=PDF_OUTPUT_LIMIT,
        )
    text = raw.decode("utf-8", errors="replace")
    blank_pages = [
        start_page + index
        for index, page in enumerate(text.split("\f")[: end - start_page + 1])
        if not page.strip()
    ]
    result.update(
        text=text[:max_chars],
        total_pages=total,
        start_page=start_page,
        end_page=end,
        complete=start_page == 1 and end == total and len(text) <= max_chars and not blank_pages,
        extraction="poppler",
        blank_pages=blank_pages,
    )
    if len(text) > max_chars:
        result["content_truncated"] = True
    if end < total:
        result["next_page"] = end + 1
    if blank_pages:
        result["warning"] = "Some pages have no extractable text and may require OCR."
    result["note"] = (
        "Text extraction does not describe images, diagrams or guarantee reading order."
    )
    return result
