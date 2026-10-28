"""Bounded read-only Canvas transport and safe metadata-derived file retrieval.

An injected HTTPX transport is a *trusted testing seam*: it bypasses DNS pinning.
Production connections never use environment proxies, resolve public addresses only,
and pin the TCP destination while retaining the original TLS SNI and Host header.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import math
import re
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .catalog import Operation
from .policy import PolicyError, build_url, operation_path, validate_continuation, validate_origin


class CanvasError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def _split_link(value: str, delimiter: str) -> list[str]:
    """Split RFC 8288 separators, respecting quoted strings and URI brackets."""
    parts: list[str] = []
    quoted = escaped = angle = False
    start = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"' and not angle:
            quoted = not quoted
        elif not quoted:
            if char == "<":
                if angle:
                    raise CanvasError("pagination", "Malformed pagination URI brackets.")
                angle = True
            elif char == ">":
                if not angle:
                    raise CanvasError("pagination", "Malformed pagination URI brackets.")
                angle = False
            elif char == delimiter and not angle:
                parts.append(value[start:index].strip())
                start = index + 1
    if quoted or escaped or angle:
        raise CanvasError("pagination", "Canvas returned an incomplete pagination header.")
    parts.append(value[start:].strip())
    return parts


def _next_link(header: str) -> str | None:
    if not header:
        return None
    next_url = None
    for link in _split_link(header, ","):
        fields = _split_link(link, ";")
        if not re.fullmatch(r"<[^<>]+>", fields[0]):
            raise CanvasError("pagination", "Canvas returned a malformed pagination header.")
        relations = None
        for field in fields[1:]:
            match = re.fullmatch(
                r'([!#$%&\'*+.^_`|~0-9A-Za-z-]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^\s";]+)', field
            )
            if not match:
                raise CanvasError("pagination", "Canvas returned a malformed pagination parameter.")
            if match[1].lower() == "rel":
                if relations is not None:
                    raise CanvasError(
                        "pagination", "Canvas returned duplicate pagination relations."
                    )
                relations = match[2].strip('"').lower().split()
        if relations and "next" in relations:
            if next_url is not None:
                raise CanvasError("pagination", "Canvas returned ambiguous pagination links.")
            next_url = fields[0][1:-1]
    return next_url


def _decode_json(raw: bytes) -> Any:
    # The byte cap alone permits millions of tiny objects or arbitrarily deep
    # trees. Inspect structure outside strings before allocating the parsed tree.
    depth = separators = 0
    in_string = escaped = False
    for char in raw:
        if escaped:
            escaped = False
        elif in_string and char == 92:
            escaped = True
        elif char == 34:
            in_string = not in_string
        elif not in_string:
            if char in (91, 123):
                depth += 1
                if depth > 100:
                    raise CanvasError("upstream", "Canvas JSON exceeds the nesting limit.")
            elif char in (93, 125):
                depth -= 1
            elif char == 44:
                separators += 1
                if separators > 200_000:
                    raise CanvasError(
                        "too_large", "Canvas JSON is too complex; request smaller pages."
                    )

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number

    def invalid_constant(_: str) -> None:
        raise ValueError("Nonstandard JSON constant")

    try:
        return json.loads(
            raw.decode("utf-8-sig"), parse_constant=invalid_constant, parse_float=finite_float
        )
    except (ValueError, UnicodeError, RecursionError):
        raise CanvasError("upstream", "Canvas did not return valid JSON.") from None


async def _raw_chunks(response):
    if response.is_stream_consumed:
        # MockTransport JSON fixtures may already have an in-memory response.
        yield response.content
    else:
        async for chunk in response.aiter_raw(chunk_size=65536):
            yield chunk


async def _public_address(host: str) -> str:
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        ips = list(dict.fromkeys(info[4][0] for info in addresses))

        def unsafe(ip: str) -> bool:
            address = ipaddress.ip_address(ip)
            return (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or (
                    isinstance(address, ipaddress.IPv6Address)
                    and (address.sixtofour is not None or address.teredo is not None)
                )
            )

        if not ips or any(unsafe(ip) for ip in ips):
            raise CanvasError(
                "unsafe_destination",
                "Network destination must resolve only to public IP addresses.",
            )
        return ips[0]
    except (socket.gaierror, ValueError):
        raise CanvasError("network", "Could not resolve the network destination.", True) from None


class CanvasClient:
    def __init__(
        self, origin: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        try:
            self.origin = validate_origin(origin)
        except PolicyError as error:
            raise CanvasError("policy", str(error)) from None
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise CanvasError("auth", "A valid Canvas access token is required.")
        self._token = token
        self._test_transport = transport is not None
        # The public transport interface avoids AsyncClient's INFO-level URL
        # logging (signed file URLs are credentials) and cookie persistence.
        self._transport = (
            transport
            if transport is not None
            else httpx.AsyncHTTPTransport(
                trust_env=False,
                limits=httpx.Limits(max_keepalive_connections=0, max_connections=4),
            )
        )
        self._request_lock = asyncio.Lock()

    async def __aenter__(self) -> CanvasClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._transport.aclose()

    @asynccontextmanager
    async def _stream(self, url, headers, extensions):
        request = httpx.Request(
            "GET",
            url,
            headers=headers,
            extensions={**extensions, "timeout": httpx.Timeout(20).as_dict()},
        )
        response = await self._transport.handle_async_request(request)
        response.request = request
        try:
            yield response
        finally:
            await response.aclose()

    async def _request(
        self, url: str, *, authorize: bool, max_bytes: int, redirects: bool = False
    ) -> tuple[bytes, httpx.Headers, int]:
        """One destination, bounded streaming and retries. Never auto-follow redirects."""
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.port not in (None, 443)
            or "\\" in url
            or any(ord(char) < 33 for char in url)
        ):
            raise CanvasError("unsafe_destination", "Only public HTTPS destinations are permitted.")
        if authorize and (parsed.scheme + "://" + parsed.netloc).lower() != self.origin:
            raise CanvasError("policy", "Canvas credentials cannot be sent to another origin.")
        async with self._request_lock:
            for attempt in range(3):
                destination = httpx.URL(url)
                headers = {
                    "Accept": "application/json" if not redirects else "*/*",
                    "User-Agent": "folava-mcp/0.1",
                    "Accept-Encoding": "identity",
                }
                extensions: dict[str, Any] = {}
                if not self._test_transport:
                    address = await _public_address(parsed.hostname)
                    destination = destination.copy_with(host=address)
                    headers["Host"] = parsed.netloc
                    extensions["sni_hostname"] = parsed.hostname
                if authorize:
                    headers["Authorization"] = "Bearer " + self._token
                try:
                    async with self._stream(destination, headers, extensions) as response:
                        status = response.status_code
                        if status == 429 or status in (500, 502, 503, 504):
                            if attempt == 2:
                                raise CanvasError(
                                    "rate_limit" if status == 429 else "upstream",
                                    "Canvas is temporarily unavailable; retry later.",
                                    True,
                                )
                            try:
                                delay = min(
                                    2.0,
                                    max(
                                        0.0,
                                        float(
                                            response.headers.get("retry-after", 0.25 * 2**attempt)
                                        ),
                                    ),
                                )
                            except ValueError:
                                delay = 0.25 * 2**attempt
                        elif 300 <= status < 400 and redirects:
                            return b"", response.headers, status
                        elif status == 401:
                            raise CanvasError(
                                "auth", "Canvas rejected the credential; sign in again."
                            )
                        elif status == 403:
                            raise CanvasError(
                                "forbidden", "Canvas does not permit access to this resource."
                            )
                        elif status == 404:
                            raise CanvasError(
                                "not_found", "Canvas resource was not found or is not visible."
                            )
                        elif not 200 <= status < 300:
                            raise CanvasError("upstream", "Canvas returned an unexpected response.")
                        else:
                            # Reject compressed bodies before HTTPX allocates decoder output.
                            if (
                                response.headers.get("content-encoding", "identity").strip().lower()
                                != "identity"
                            ):
                                raise CanvasError(
                                    "encoding",
                                    "Compressed responses are unsupported; use identity encoding.",
                                )
                            length = response.headers.get("content-length", "")
                            if length.isdigit() and int(length) > max_bytes:
                                raise CanvasError(
                                    "too_large", "Response exceeds the configured byte limit."
                                )
                            body = bytearray()
                            async for chunk in _raw_chunks(response):
                                if len(body) + len(chunk) > max_bytes:
                                    raise CanvasError(
                                        "too_large", "Response exceeds the configured byte limit."
                                    )
                                body.extend(chunk)
                            return bytes(body), response.headers, status
                    await asyncio.sleep(delay)
                except (httpx.HTTPError, OSError):
                    if attempt == 2:
                        raise CanvasError(
                            "network", "Network request failed; retry later.", True
                        ) from None
                    await asyncio.sleep(0.25 * 2**attempt)
        raise CanvasError("network", "Network request failed.", True)

    async def read(
        self,
        operation: str,
        path: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        *,
        max_pages: int = 1,
    ) -> dict[str, Any]:
        try:
            if type(max_pages) is not int or not 1 <= max_pages <= 20:
                raise PolicyError("max_pages must be between 1 and 20.")
            op, request_path = operation_path(operation, path)
            url = build_url(self.origin, op, request_path, query)
            async with asyncio.timeout(90):
                return await self._read_pages(op, request_path, url, max_pages)
        except PolicyError as error:
            raise CanvasError("policy", str(error)) from None
        except TimeoutError:
            raise CanvasError("timeout", "Canvas request exceeded its time limit.", True) from None
        except (ValueError, UnicodeError):
            raise CanvasError("upstream", "Canvas returned an invalid response.") from None

    async def _read_pages(
        self, op: Operation, path: str, url: str, max_pages: int
    ) -> dict[str, Any]:
        data: Any = None
        pages = 0
        remaining = 20_000_000
        seen: set[str] = set()
        next_url: str | None = url
        while next_url and pages < max_pages:
            if next_url in seen:
                raise CanvasError("pagination", "Canvas returned a pagination cycle.")
            seen.add(next_url)
            raw, headers, _ = await self._request(
                next_url, authorize=True, max_bytes=min(10_000_000, remaining)
            )
            remaining -= len(raw)
            page = _decode_json(raw)
            if op.id == "quiz_submissions" and (
                not isinstance(page, dict)
                or not isinstance(page.get("quiz_submissions"), list)
                or any(not isinstance(values, list) for values in page.values())
            ):
                raise CanvasError("upstream", "Invalid quiz submissions envelope.")
            if pages == 0:
                data = page
            elif op.id == "quiz_submissions" and isinstance(data, dict) and isinstance(page, dict):
                for key, values in page.items():
                    if not isinstance(values, list) or not isinstance(data.get(key, []), list):
                        raise CanvasError("pagination", "Invalid quiz submissions envelope.")
                    data.setdefault(key, []).extend(values)
            elif isinstance(data, list) and isinstance(page, list):
                data.extend(page)
            else:
                raise CanvasError("pagination", "Paginated Canvas response must be a list.")
            if isinstance(data, list) and len(data) > 20_000:
                raise CanvasError(
                    "too_large", "Response exceeds the item limit; request smaller pages."
                )
            pages += 1
            candidate = _next_link(headers.get("link", ""))
            next_url = (
                validate_continuation(candidate, self.origin, op, path) if candidate else None
            )
            if op.id == "quiz_submissions":
                if not isinstance(data, dict) or not isinstance(data.get("quiz_submissions"), list):
                    raise CanvasError("upstream", "Invalid quiz submissions envelope.")
                if sum(len(value) for value in data.values() if isinstance(value, list)) > 20_000:
                    raise CanvasError("too_large", "Response exceeds the item limit.")
            if next_url and not isinstance(data, list) and op.id != "quiz_submissions":
                raise CanvasError(
                    "pagination", "Canvas returned pagination for a non-list response."
                )
        result = {
            "data": data,
            "source_url": self.origin + path,
            "fetched_at": datetime.now(UTC).isoformat(),
            "pages": pages,
            "complete": next_url is None,
        }
        if next_url:
            result["next_url"] = next_url
        return result

    async def file(self, file_id: str, *, max_bytes: int = 5_000_000) -> dict[str, Any]:
        if type(max_bytes) is not int or not 1 <= max_bytes <= 20_000_000:
            raise CanvasError("policy", "max_bytes must be between 1 and 20000000.")
        try:
            async with asyncio.timeout(90):
                envelope = await self.read("file", {"file_id": file_id})
                metadata = envelope["data"]
                if not isinstance(metadata, dict):
                    raise CanvasError("upstream", "Canvas returned invalid file metadata.")
                if metadata.get("locked_for_user") or metadata.get("hidden_for_user"):
                    raise CanvasError("forbidden", "Canvas file is locked or hidden for this user.")
                if isinstance(metadata.get("size"), (int, float)) and metadata["size"] > max_bytes:
                    raise CanvasError("too_large", "File exceeds the configured byte limit.")
                url = metadata.get("url")
                if not isinstance(url, str):
                    raise CanvasError("upstream", "Canvas file has no download URL.")
                authorize = True
                seen: set[str] = set()
                for _ in range(6):
                    parsed = urlsplit(url)
                    same_origin = (parsed.scheme + "://" + parsed.netloc).lower() == self.origin
                    authorize = authorize and same_origin
                    # Only the file download UI route is allowed on the credentialed origin.
                    if same_origin and not re.fullmatch(
                        r"/(?:[^/?]+/[^/?]+/)?files/[A-Za-z0-9_-]+/download", parsed.path
                    ):
                        raise CanvasError(
                            "policy", "Canvas file metadata has an unexpected download path."
                        )
                    if url in seen:
                        raise CanvasError("redirect", "File download contains a redirect cycle.")
                    seen.add(url)
                    body, headers, status = await self._request(
                        url, authorize=authorize, max_bytes=max_bytes, redirects=True
                    )
                    if 300 <= status < 400:
                        location = headers.get("location")
                        if not location:
                            raise CanvasError("redirect", "File download redirect has no location.")
                        url = urljoin(url, location)
                        continue
                    if status != 200 or "content-range" in headers:
                        raise CanvasError(
                            "upstream", "File download did not return a complete response."
                        )
                    mime = (
                        headers.get(
                            "content-type",
                            str(metadata.get("content-type", "application/octet-stream")),
                        )
                        .split(";")[0]
                        .strip()
                    )
                    # Do not propagate signed URLs into the file tool response.
                    safe_metadata = {
                        key: value
                        for key, value in metadata.items()
                        if key
                        in (
                            "id",
                            "display_name",
                            "filename",
                            "size",
                            "created_at",
                            "updated_at",
                            "content-type",
                        )
                    }
                    result = {
                        "metadata": safe_metadata,
                        "mime_type": mime,
                        "size": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "source_url": envelope["source_url"],
                        "fetched_at": envelope["fetched_at"],
                    }
                    if mime.startswith("text/") or mime in ("application/json", "application/xml"):
                        try:
                            result["text"] = body.decode("utf-8")
                        except UnicodeDecodeError:
                            result["content_base64"] = base64.b64encode(body).decode("ascii")
                    else:
                        result["content_base64"] = base64.b64encode(body).decode("ascii")
                    return result
                raise CanvasError("redirect", "File download exceeded the redirect limit.")
        except TimeoutError:
            raise CanvasError("timeout", "File download exceeded its time limit.", True) from None
        except (ValueError, UnicodeError):
            raise CanvasError("upstream", "Canvas returned an invalid file response.") from None
