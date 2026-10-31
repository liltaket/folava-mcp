import base64
import json

import httpx
import pytest

from folava_mcp.client import CanvasClient, CanvasError
from folava_mcp.policy import PolicyError, validate_storage_download

ORIGIN = "https://canvas.example"
HOST = "inst-fs-dub-prod.inscloudgate.net"
PATH = "/files/12345678-1234-1234-1234-123456789abc/lecture%20notes.pdf"


def encoded(value):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def signed_url(path=PATH, *, claims=None, header=None):
    payload = {
        "iat": 1,
        "exp": 2,
        "user_id": None,
        "host": None,
        "resource": path,
        "jti": "fixture",
        **(claims or {}),
    }
    token = ".".join(
        [
            encoded(header if header is not None else {"typ": "JWT", "alg": "HS512"}),
            encoded(payload),
            encoded(b"x" * 64),
        ]
    )
    return f"https://{HOST}{path}?token={token}"


@pytest.mark.parametrize("filename", ["lecture%20notes.pdf", "%C3%B6vningar.pdf", "simple.pdf"])
def test_instfs_content_capability_preserved_exactly(filename):
    url = signed_url(PATH.rsplit("/", 1)[0] + "/" + filename)
    assert validate_storage_download(url, ORIGIN) == url


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "metadata",
        "%6detadata",
        "duplicate",
        ".",
        "..",
        "%2e%2e",
        "%2Fother",
        "%5Cother",
        "%00",
        "%0A",
        "%7f",
        "%252Fother",
        "%GG",
        "nested/file.pdf",
    ],
)
def test_instfs_rejects_ambiguous_and_non_content_paths(filename):
    url = signed_url(PATH.rsplit("/", 1)[0] + "/" + filename)
    with pytest.raises(PolicyError):
        validate_storage_download(url, ORIGIN)


@pytest.mark.parametrize(
    "replacement",
    [
        "https://inst-fs-dub-prod.inscloudgate.net.evil.example",
        "https://inst-fs-other-prod.inscloudgate.net",
        "https://inscloudgate.net",
        "https://user:private@inst-fs-dub-prod.inscloudgate.net",
        "https://inst-fs-dub-prod.inscloudgate.net:8443",
        "http://inst-fs-dub-prod.inscloudgate.net",
    ],
)
def test_instfs_host_and_https_boundary(replacement):
    with pytest.raises(PolicyError):
        validate_storage_download(signed_url().replace(f"https://{HOST}", replacement), ORIGIN)


@pytest.mark.parametrize(
    "claims",
    [
        {"user_id": "student"},
        {"host": "canvas.example"},
        {"resource": "/different"},
        {"resource": PATH.replace("%20", " ")},
        {"fallback_url": "https://canvas.example"},
        {"capture_url": "https://canvas.example"},
        {"acting_as_user_id": "student"},
        {"tenant_auth": "unexpected"},
        {"iat": True},
        {"exp": "tomorrow"},
        {"exp": 1},
        {"jti": ""},
        {"internal": True},
    ],
)
def test_instfs_identity_callback_and_malformed_claims_rejected(claims):
    with pytest.raises(PolicyError):
        validate_storage_download(signed_url(claims=claims), ORIGIN)


@pytest.mark.parametrize("suffix", ["&download=1", "&token=duplicate", "#fragment", "&extra=1"])
def test_instfs_extra_query_or_fragment_rejected(suffix):
    with pytest.raises(PolicyError):
        validate_storage_download(signed_url() + suffix, ORIGIN)


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "none", "typ": "JWT"},
        {"alg": "HS256", "typ": "JWT"},
        b'{"typ":"JWT","alg":"none","alg":"HS512"}',
        [],
    ],
)
def test_instfs_bad_or_duplicate_header_fields_rejected(header):
    with pytest.raises(PolicyError):
        validate_storage_download(signed_url(header=header), ORIGIN)


@pytest.mark.parametrize("query", ["", "token=invalid", "token=" + "a" * 17000 + ".a.a"])
def test_instfs_malformed_or_oversized_tokens_rejected(query):
    with pytest.raises(PolicyError):
        validate_storage_download(signed_url().split("?")[0] + "?" + query, ORIGIN)


def test_instfs_duplicate_payload_keys_rejected():
    url = signed_url()
    # Replace just the JWT payload, preserving its URL/header prefix.
    token_prefix, token = url.split("?token=")
    header, payload, signature = token.split(".")
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    duplicate = raw[:-1] + b', "user_id": null}'
    bad = token_prefix + "?token=" + ".".join([header, encoded(duplicate), signature])
    with pytest.raises(PolicyError):
        validate_storage_download(bad, ORIGIN)


@pytest.mark.parametrize("redirect", [None, "https://canvas.example/files/1/download", "/session"])
async def test_instfs_transport_isolates_credentials_and_validates_redirects(redirect, caplog):
    seen = []
    capability = signed_url()

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/files/1":
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(200, json={"id": 1, "size": 4})
        if request.url.path == "/api/v1/files/1/public_url":
            return httpx.Response(200, json={"public_url": capability})
        assert str(request.url) == capability
        assert "authorization" not in request.headers and "cookie" not in request.headers
        if redirect:
            return httpx.Response(302, headers={"location": redirect})
        return httpx.Response(200, content=b"file", headers={"content-type": "text/plain"})

    async with CanvasClient(ORIGIN, "secret", transport=httpx.MockTransport(handler)) as client:
        if redirect:
            with pytest.raises(CanvasError) as error:
                await client.file("1")
            assert error.value.code == "policy"
        else:
            result = await client.file("1")
            assert result["text"] == "file" and "token=" not in json.dumps(result)
    assert len(seen) == 3
    assert "token=" not in caplog.text


def cdn_url(*, path=None, claims=None, header=None):
    path = path or "/87654321-1234-1234-1234-123456789abc/lecture%20notes.pdf"
    payload = {"iat": 1, "exp": 2, "resource": path, "jti": "fixture", "tenant": "fixture"}
    payload.update(claims or {})
    token = ".".join(
        [
            encoded(header or {"typ": "JWT", "alg": "HS512", "kid": "cdn"}),
            encoded(payload),
            encoded(b"x" * 64),
        ]
    )
    return f"https://cdn.{HOST}{path}?token={token}&content_type=application%2Fpdf"


def test_cdn_requires_validated_instfs_source_and_binds_filename_not_internal_uuid():
    source, target = signed_url(), cdn_url()
    assert validate_storage_download(target, ORIGIN, instfs_source=source) == target
    with pytest.raises(PolicyError):
        validate_storage_download(target, ORIGIN)
    with pytest.raises(PolicyError):
        validate_storage_download(target, ORIGIN, instfs_source="https://bucket.s3.amazonaws.com/x")


@pytest.mark.parametrize(
    "target",
    [
        cdn_url(path="/87654321-1234-1234-1234-123456789abc/another.pdf"),
        cdn_url(claims={"resource": "/different"}),
        cdn_url(claims={"user_id": "student"}),
        cdn_url(claims={"tenant": ""}),
        cdn_url(claims={"fallback_url": "https://canvas.example"}),
        cdn_url(header={"typ": "JWT", "alg": "HS512"}),
        cdn_url() + "&extra=1",
        cdn_url() + "&token=duplicate",
        cdn_url().replace("application%2Fpdf", "text%2Fhtml%0Aother"),
        cdn_url().replace("cdn." + HOST, "cdn.evil.example"),
    ],
)
def test_cdn_rejects_changed_file_claims_headers_query_and_host(target):
    with pytest.raises(PolicyError):
        validate_storage_download(target, ORIGIN, instfs_source=signed_url())


@pytest.mark.parametrize("terminal_redirect", [None, "https://bucket.s3.amazonaws.com/other"])
async def test_instfs_cdn_chain_has_no_credentials_and_accepts_only_terminal_content(
    terminal_redirect,
):
    source, target = signed_url(), cdn_url()
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/files/1":
            return httpx.Response(200, json={"id": 1})
        if request.url.path == "/api/v1/files/1/public_url":
            return httpx.Response(200, json={"public_url": source})
        assert "authorization" not in request.headers and "cookie" not in request.headers
        if str(request.url) == source:
            return httpx.Response(302, headers={"location": target, "set-cookie": "secret=private"})
        assert str(request.url) == target
        if terminal_redirect:
            return httpx.Response(302, headers={"location": terminal_redirect})
        return httpx.Response(200, content=b"file", headers={"content-type": "text/plain"})

    async with CanvasClient(ORIGIN, "secret", transport=httpx.MockTransport(handler)) as client:
        if terminal_redirect:
            with pytest.raises(CanvasError) as error:
                await client.file("1")
            assert error.value.code == "redirect"
        else:
            assert (await client.file("1"))["text"] == "file"
    assert len(seen) == 4


async def test_initial_cdn_pointer_is_rejected_before_request():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/files/1":
            return httpx.Response(200, json={"id": 1})
        assert request.url.path == "/api/v1/files/1/public_url"
        return httpx.Response(200, json={"public_url": cdn_url()})

    async with CanvasClient(ORIGIN, "secret", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CanvasError) as error:
            await client.file("1")
        assert error.value.code == "policy"
    assert len(seen) == 2
