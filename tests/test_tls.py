"""Real HTTPX/httpcore TLS handshake: a mocked resolver, no external service."""

import asyncio
import ipaddress
import ssl
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from folava_mcp.client import CanvasClient, CanvasError


@pytest.mark.parametrize("certificate_name", ["canvas.test", "wrong.test"])
async def test_pinned_ip_verifies_original_hostname(tmp_path, monkeypatch, certificate_name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, certificate_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(certificate_name)]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_file, key_file)
    client_context = ssl.create_default_context(cafile=str(cert_file))
    requests = []

    async def handle(reader, writer):
        try:
            requests.append(await reader.readuntil(b"\r\n\r\n"))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n[]")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]

    class LocalPortTransport(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            # Only remap the test listener's port; real HTTPX TLS verification is intact.
            request.url = request.url.copy_with(port=port)
            assert ipaddress.ip_address(request.url.host).is_loopback
            return await super().handle_async_request(request)

    async def resolve(host):
        assert host == "canvas.test"
        return "127.0.0.1"  # Controlled test resolver; production denies this address.

    monkeypatch.setattr("folava_mcp.client._public_address", resolve)
    async with server:
        async with CanvasClient(
            "https://canvas.test",
            "test-secret",
            transport=LocalPortTransport(verify=client_context),
        ) as client:
            client._test_transport = False
            if certificate_name == "canvas.test":
                result = await client.read("courses")
                assert result["complete"]
                assert b"Host: canvas.test\r\n" in requests[0]
                assert b"Authorization: Bearer test-secret\r\n" in requests[0]
            else:
                with pytest.raises(CanvasError) as error:
                    await client.read("courses")
                assert error.value.code == "network"
                assert not requests
