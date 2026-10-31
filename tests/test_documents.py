import asyncio
import base64
import shutil
import sys

import pytest

from folava_mcp.client import CanvasError
from folava_mcp.documents import _run, file_text


def pdf_bytes(texts):
    """Small real PDF fixture, including its cross-reference table."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{4 + i * 2} 0 R".encode() for i in range(len(texts)))
        + f"] /Count {len(texts)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(texts):
        stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode()
        objects.extend(
            [
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 3 0 R >> >> "
                + f"/Contents {5 + i * 2} 0 R >>".encode(),
                f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            ]
        )
    body = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    body += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return body


def attachment(texts):
    return {
        "mime_type": "application/pdf",
        "sha256": "fixture-digest",
        "source_url": "https://canvas.example/api/v1/files/1",
        "content_base64": base64.b64encode(pdf_bytes(texts)).decode(),
    }


poppler = pytest.mark.skipif(
    not all(shutil.which(command) for command in ("pdfinfo", "pdftotext")),
    reason="Real PDF extraction needs optional Poppler tools",
)


@poppler
async def test_real_pdf_text_page_window_and_provenance():
    source = attachment(["First page", "Second page"])
    result = await file_text(source)
    assert "First page" in result["text"] and "Second page" in result["text"]
    assert result["complete"] and result["total_pages"] == 2
    assert result["sha256"] == source["sha256"] and result["source_url"] == source["source_url"]
    assert "content_base64" not in result
    first = await file_text(source, max_pages=1)
    assert "First page" in first["text"] and "Second page" not in first["text"]
    assert not first["complete"] and first["next_page"] == 2
    second = await file_text(source, start_page=2)
    assert "Second page" in second["text"] and not second["complete"]
    assert "next_page" not in second


@poppler
async def test_blank_and_truncated_pdf_never_claim_complete():
    blank = await file_text(attachment(["A readable page", ""]))
    assert blank["blank_pages"] == [2] and not blank["complete"]
    assert "OCR" in blank["warning"]
    clipped = await file_text(attachment(["Long enough"]), max_chars=4)
    assert clipped["text"] == "Long" and clipped["content_truncated"]
    assert not clipped["complete"]
    with pytest.raises(CanvasError) as error:
        await file_text(attachment(["one"]), start_page=2)
    assert error.value.code == "input"


async def test_missing_poppler_and_bad_documents_have_actionable_errors(monkeypatch):
    monkeypatch.setattr("folava_mcp.documents.shutil.which", lambda _: None)
    with pytest.raises(CanvasError) as error:
        await file_text(attachment(["one"]))
    assert error.value.code == "pdf_dependency"
    with pytest.raises(CanvasError) as error:
        await file_text({"mime_type": "application/pdf", "content_base64": "bad!"})
    assert error.value.code == "upstream"
    with pytest.raises(CanvasError) as error:
        await file_text({"mime_type": "application/pdf", "content_base64": "bm90LXBkZg=="})
    assert error.value.code == "pdf_unreadable"
    with pytest.raises(CanvasError) as error:
        await file_text({"mime_type": "application/zip", "content_base64": ""})
    assert error.value.code == "unsupported_media"


async def test_plain_text_clips_without_binary_payload():
    result = await file_text({"text": "hello", "mime_type": "text/plain"}, max_chars=3)
    assert result["text"] == "hel" and not result["complete"] and result["content_truncated"]


async def test_parser_process_is_killed_on_timeout_overflow_and_cancellation(monkeypatch):
    original_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("folava_mcp.documents.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("folava_mcp.documents.PDF_TIMEOUT", 0.1)
    with pytest.raises(CanvasError) as error:
        await _run(sys.executable, "-c", "import time; time.sleep(10)", limit=100)
    assert error.value.code == "timeout" and processes[-1].returncode is not None
    monkeypatch.setattr("folava_mcp.documents.PDF_TIMEOUT", 5)
    with pytest.raises(CanvasError) as error:
        await _run(sys.executable, "-c", "print('x' * 1000)", limit=100)
    assert error.value.code == "too_large" and processes[-1].returncode is not None
    task = asyncio.create_task(_run(sys.executable, "-c", "import time; time.sleep(10)", limit=100))
    while len(processes) < 3:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[-1].returncode is not None


async def test_parser_overflow_cleanup_drains_a_full_pipe(monkeypatch):
    original_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        processes.append(process)
        # Let the producer fill the OS/asyncio buffers before the consumer reads.
        await asyncio.sleep(0.1)
        return process

    monkeypatch.setattr("folava_mcp.documents.asyncio.create_subprocess_exec", spawn)
    with pytest.raises(CanvasError) as error:
        await asyncio.wait_for(
            _run(sys.executable, "-c", "import sys; sys.stdout.write('x' * 5000000)", limit=100),
            timeout=3,
        )
    assert error.value.code == "too_large" and processes[0].returncode is not None


@poppler
async def test_corrupt_pdf_errors_do_not_echo_parser_output():
    with pytest.raises(CanvasError) as error:
        await file_text(
            {
                "mime_type": "application/pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4\nprivate-data").decode(),
            }
        )
    assert error.value.code == "pdf_unreadable" and "private-data" not in str(error.value)


@poppler
async def test_pdf_tool_downloads_and_extracts_without_returning_capability():
    import httpx

    from folava_mcp.client import CanvasClient
    from folava_mcp.server import create_server

    body = pdf_bytes(["Readable attachment"])

    def handler(request):
        if request.url.path == "/api/v1/files/1":
            return httpx.Response(200, json={"id": 1, "size": len(body)})
        if request.url.path == "/api/v1/files/1/public_url":
            return httpx.Response(
                200, json={"public_url": "https://bucket.s3.amazonaws.com/object?Signature=private"}
            )
        assert "authorization" not in request.headers
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    server = create_server(
        client_factory=lambda: CanvasClient(
            "https://canvas.example", "secret", transport=httpx.MockTransport(handler)
        )
    )
    result = (await server.call_tool("canvas_file_text", {"file_id": "1"})).structured_content
    assert result["complete"] and "Readable attachment" in result["text"]
    assert result["total_pages"] == 1 and result["sha256"]
    assert "content_base64" not in result and "Signature" not in str(result)


async def test_file_text_tool_preserves_normal_text_budget():
    from folava_mcp.demo import DemoClient
    from folava_mcp.server import create_server

    class Client(DemoClient):
        async def file(self, *args, **kwargs):
            return {"text": "ö" * 20_000, "mime_type": "text/plain"}

    result = (
        await create_server(client_factory=Client).call_tool("canvas_file_text", {"file_id": "601"})
    ).structured_content
    assert result["complete"] and len(result["text"]) == 20_000
