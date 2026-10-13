"""Portable trusted roots for the launcher's Python HTTPS requests."""

from __future__ import annotations

import json
import os
import pathlib
import ssl
import urllib.error
import urllib.request

import certifi


def configure_certificates():
    """Use bundled roots unless the user explicitly selected a CA file."""
    configured = os.environ.get("SSL_CERT_FILE")
    if configured:
        return pathlib.Path(configured)
    bundle = pathlib.Path(certifi.where())
    if not bundle.is_file():
        raise RuntimeError(
            "The launcher's trusted certificate bundle is missing. Reinstall the package."
        )
    os.environ["SSL_CERT_FILE"] = str(bundle)
    return bundle


def check_network():
    """Verify packaged trust and public service TLS without signing in."""
    bundle = configure_certificates()
    context = ssl.create_default_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.cert_store_stats()["x509_ca"] > 0, "Trusted root certificates were not loaded"
    print(
        json.dumps(
            {
                "certificate_bundle": str(bundle),
                "trusted_roots": context.cert_store_stats()["x509_ca"],
            }
        ),
        flush=True,
    )
    endpoints = {
        "Modrinth": "https://api.modrinth.com/v2/tag/loader",
        "GitHub updates": "https://api.github.com/repos/Zazuzin/BreakBlocks-Launcher/releases?per_page=1",
        "Minecraft metadata": "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
    }
    for service, url in endpoints.items():
        request = urllib.request.Request(
            url, headers={"User-Agent": "BreakBlocks-Launcher certificate check"}
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                response.read(1)
        except urllib.error.HTTPError:
            # Even a rate-limit response proves the TLS handshake verified.
            pass
        print(f"Verified HTTPS certificate: {service}", flush=True)
    return 0
