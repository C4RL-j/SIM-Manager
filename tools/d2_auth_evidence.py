"""Development-only public D2 source inspection; never logs in or reads sessions.

The normal application must not import this tool. Output contains only reviewed
static names, fixed-format paths, hashes, and candidate request metadata. Source
strings are never printed. Static references do not verify a working protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import time

if __package__:
    from . import d2_source_evidence as evidence
else:
    import d2_source_evidence as evidence


ORIGIN = "https://192.168.1.1"
MAX_BYTES = 4 * 1024 * 1024
MAX_ASSETS = 16
ASSET = re.compile(r"/static/js/(?:app\.[a-f0-9]{8}|chunk-[a-zA-Z0-9_-]+\.[a-f0-9]{8})\.js")
# The active app's root route explicitly loads chunk-ff19fe88; its full path
# was already established by the fixed Task 004 firmware file index.
AUTH_DETAIL_ASSETS = ("/static/js/chunk-ff19fe88.a86a0aee.js",)
AUTH_SEGMENTS = frozenset(
    "web v1 auth authentication login logout user users session token signin "
    "signout system setting management account admin check checklogin "
    "logincheck captcha gettoken refresh".split()
)
AUTH_OPERATIONS = frozenset(
    "auth authentication login logout session token signin signout checklogin "
    "logincheck captcha gettoken refresh".split()
)
REVIEWED_NAMES = frozenset({
    "Authorization", "withCredentials", "localStorage", "sessionStorage",
    "Cookie", "cookie", "Set-Cookie", "X-Token", "X-CSRF-Token", "Bearer",
    "username", "userName", "Username", "UserName", "password", "Password",
    "token", "Token", "access_token", "accessToken", "refresh_token",
    "code", "data", "msg", "expires", "expires_in", "expiry", "timeout",
    "md5", "MD5", "sha256", "SHA256", "SHA1", "AES", "RSA", "JSEncrypt",
    "CryptoJS", "btoa", "Base64", "encrypt", "encodeURIComponent",
    "docname", "pass", "userrole", "FirstLogin", "timeOut",
})


def _asset(value: str) -> bool:
    return bool(ASSET.fullmatch(value))


def _auth_endpoint(value: str) -> bool:
    if not value.startswith("/web/v1/") or len(value) > 160:
        return False
    segments = value.strip("/").split("/")
    return (
        all(segment in AUTH_SEGMENTS for segment in segments)
        and bool(set(segments) & AUTH_OPERATIONS)
    )


class _PublicAssets(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paths: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ("script", "link"):
            return
        key = "src" if tag == "script" else "href"
        for name, value in attrs:
            if name == key and value is not None:
                candidate = "/" + value if value.startswith("static/") else value
                if _asset(candidate):
                    self.paths.add(candidate)


def public_assets(html: str) -> list[str]:
    """Return fixed-format script names, never arbitrary URLs or attributes."""
    parser = _PublicAssets()
    parser.feed(html[:MAX_BYTES])
    return sorted(parser.paths)[:MAX_ASSETS]


def summarize_auth_source(source: str, path: str) -> dict:
    """Summarize lexical evidence; no JavaScript execution or raw string output."""
    if not isinstance(source, str):
        raise ValueError("Source must be text.") from None
    tokens = evidence._tokens(source[:MAX_BYTES])
    names = {value for kind, value in tokens if kind in ("identifier", "string") and value in REVIEWED_NAMES}
    frames: list[dict[str, list[str | None]]] = []
    requests: set[tuple[str, str]] = set()
    for index, (kind, value) in enumerate(tokens):
        if kind == "punctuation" and value == "{":
            frames.append({"url": [], "method": []})
        elif kind == "punctuation" and value == "}":
            if not frames:
                continue
            frame = frames.pop()
            if len(frame["url"]) == len(frame["method"]) == 1:
                url, method = frame["url"][0], frame["method"][0]
                if url is not None and method is not None and _auth_endpoint(url):
                    if method.upper() in ("GET", "POST", "DELETE", "PUT", "PATCH", "HEAD"):
                        requests.add((method.upper(), url))
        elif (
            frames and kind in ("identifier", "string") and value in ("url", "method", "type")
            and index > 0 and tokens[index - 1][1] in ("{", ",")
            and index + 2 < len(tokens) and tokens[index + 1][1] == ":"
        ):
            literal = None
            if tokens[index + 2][0] == "string" and index + 3 < len(tokens):
                if tokens[index + 3][1] in (",", "}"):
                    literal = tokens[index + 2][1]
            frames[-1]["url" if value == "url" else "method"].append(literal)
    return {
        "source": "/opt/web" + path if _asset(path) else "omitted",
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "truncated": len(source) > MAX_BYTES,
        "reviewed_name_references": sorted(names),
        "request_candidates": [
            {"method": method, "endpoint": url, "classification": "STATIC CANDIDATE ONLY"}
            for method, url in sorted(requests)[:32]
        ],
        "other_values": "omitted",
        "meaning": "Lexical source references; request shape, transforms, token format, and runtime behavior still require review.",
    }


class _PublicConnection(http.client.HTTPSConnection):
    def close(self) -> None:
        # HTTPConnection normally closes a Connection: close socket as soon as
        # headers arrive. Delay that until the bounded body read has finished,
        # so the total deadline can update the actual socket timeout per read.
        pass

    def finish(self) -> None:
        super().close()


def _context(certificate: Path | None, allow_local_self_signed: bool) -> ssl.SSLContext:
    if certificate is not None and allow_local_self_signed:
        raise ValueError("Choose one local TLS policy.") from None
    if certificate is not None:
        # The observed firmware certificate has an IP SAN for 192.168.1.1.
        # Both chain verification and endpoint identity checking stay enabled.
        return ssl.create_default_context(cafile=str(certificate))
    if allow_local_self_signed:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context()


def fetch_public(path: str, context: ssl.SSLContext, deadline: float) -> tuple[str, str | None]:
    """GET only / or reviewed-format JS at the fixed local origin, no cookies."""
    if path != "/" and not _asset(path):
        raise ValueError("Unreviewed public asset path.") from None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Public source deadline exceeded.") from None
    connection = _PublicConnection("192.168.1.1", 443, context=context, timeout=remaining)
    chunks: list[bytes] = []
    total = 0
    certificate_sha256 = None
    response = None
    try:
        connection.request("GET", path, headers={"Accept": "text/html,application/javascript"})
        sock = connection.sock
        if sock is not None:
            certificate = sock.getpeercert(binary_form=True)
            if certificate:
                certificate_sha256 = hashlib.sha256(certificate).hexdigest()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Public source deadline exceeded.") from None
            sock.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Public source unavailable.") from None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Public source deadline exceeded.") from None
            if sock is not None:
                sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("Public source size limit exceeded.") from None
            chunks.append(chunk)
    finally:
        if response is not None:
            response.close()
        connection.finish()
    return b"".join(chunks).decode("utf-8"), certificate_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fetch-public-assets", action="store_true")
    group.add_argument("--source-file", type=Path, help="Summarize an explicitly selected local static JS file.")
    parser.add_argument("--certificate", type=Path, help="Public local-router certificate trust anchor; never a private key.")
    parser.add_argument("--allow-local-self-signed", action="store_true", help="Development-only certificate relaxation for fixed public-source GETs at 192.168.1.1.")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 60:
        parser.error("timeout must be between 0 and 60 seconds")
    try:
        if args.source_file is not None:
            with args.source_file.open("rb") as stream:
                source_bytes = stream.read(MAX_BYTES + 1)
            if len(source_bytes) > MAX_BYTES:
                raise ValueError("Public source size limit exceeded.") from None
            print(json.dumps(summarize_auth_source(source_bytes.decode("utf-8"), "/static/js/" + args.source_file.name), indent=2))
            return 0
        context = _context(args.certificate, args.allow_local_self_signed)
        deadline = time.monotonic() + args.timeout
        html, certificate_sha256 = fetch_public("/", context, deadline)
        paths = sorted(set(public_assets(html)) | set(AUTH_DETAIL_ASSETS))[:MAX_ASSETS]
        results = []
        for path in paths:
            source, _ = fetch_public(path, context, deadline)
            results.append(summarize_auth_source(source, path))
        print(json.dumps({
            "tool": "D2 public auth source evidence (development only)",
            "authentication_attempts": 0,
            "browser_state_accessed": False,
            "certificate_sha256": certificate_sha256,
            "tls_policy": "explicit local public-source relaxation" if args.allow_local_self_signed else "local certificate anchor" if args.certificate else "system trust",
            "assets": results,
        }, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Public source inspection cancelled; no credentials accessed.")
        return 130
    except (OSError, ValueError, UnicodeError, http.client.HTTPException):
        print("Public source inspection unavailable; no raw response or exception printed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
