"""TLS trust bootstrap.

On a machine behind a TLS-inspecting proxy the OS trusts the proxy's root but
Python's bundled `certifi` does not, so every HTTPS call fails with
``unable to get issuer certificate``.

``truststore`` is the fix: it makes Python's ``ssl`` module delegate
verification to the operating system's own trust store, which is what `curl`
on the same machine already uses.  That covers every client library at once -
``httpx`` (used by google-genai and huggingface_hub) builds its own SSL context
from certifi and ignores ``SSL_CERT_FILE``, so environment variables alone are
not enough.

Verification is never disabled.  Only roots the OS already trusts are added.
"""

from __future__ import annotations

import os
import ssl
import subprocess
from pathlib import Path

_MAC_KEYCHAINS = [
    "/System/Library/Keychains/SystemRootCertificates.keychain",
    "/Library/Keychains/System.keychain",
]
_BUNDLE = Path(__file__).resolve().parent.parent / ".certs" / "bundle.pem"


def _reaches(host: str, cafile: str | None = None) -> bool:
    import socket
    try:
        ctx = ssl.create_default_context(cafile=cafile)
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True
    except OSError:
        return False


def _export_system_roots() -> Path | None:
    """Concatenate certifi with the macOS keychains into one PEM.

    Fallback for when `truststore` is unavailable; only helps libraries that
    honour ``SSL_CERT_FILE``.
    """
    try:
        import certifi
    except ImportError:
        return None
    parts = [Path(certifi.where()).read_text()]
    for kc in _MAC_KEYCHAINS:
        if not Path(kc).exists():
            continue
        try:
            out = subprocess.run(["security", "find-certificate", "-a", "-p", kc],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout:
                parts.append(out.stdout)
        except (OSError, subprocess.SubprocessError):
            continue
    if len(parts) == 1:
        return None
    _BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    _BUNDLE.write_text("\n".join(parts))
    return _BUNDLE


def ensure_tls_trust(host: str = "generativelanguage.googleapis.com") -> str:
    """Make HTTPS to `host` work, and report which mechanism was used.

    Idempotent and safe to call from any entry point. Returns one of
    ``"default"``, ``"truststore"``, ``"bundle:<path>"`` or ``"unavailable"``.
    """
    if (cached := os.environ.get("OCCAM_TLS_MODE")):
        return cached

    mode = "unavailable"

    # Inject unconditionally rather than only on failure.  A bare
    # ssl.create_default_context() may well succeed here while httpx still
    # fails, because httpx pins certifi explicitly instead of using the
    # default context - so "the default works" says nothing about the
    # libraries that actually make the calls.
    try:
        import truststore
        truststore.inject_into_ssl()          # ssl now defers to the OS store
        if _reaches(host):
            mode = "truststore"
    except ImportError:
        pass

    if mode == "unavailable" and _reaches(host):
        mode = "default"

    if mode == "unavailable" and (bundle := _export_system_roots()):
        if _reaches(host, str(bundle)):
            os.environ["SSL_CERT_FILE"] = str(bundle)
            os.environ["REQUESTS_CA_BUNDLE"] = str(bundle)
            os.environ["CURL_CA_BUNDLE"] = str(bundle)
            mode = f"bundle:{bundle}"

    os.environ["OCCAM_TLS_MODE"] = mode
    return mode
