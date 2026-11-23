"""QA (Claude): Update-Verbindung im AppImage auf jeder Linux-Distribution (Zertifikate des Systems)."""

import ssl
import sys

import pytest

from app import updater


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Zertifikat-Ablagen gibt es so nur unter Linux")
def test_ssl_context_finds_the_system_certificates_even_without_default_paths(monkeypatch):
    # wie im AppImage auf Fedora/Arch: das mitgebrachte OpenSSL kennt die Ablage des Systems nicht
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    context = updater.ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.cert_store_stats()["x509_ca"] > 0


def test_ssl_context_ignores_a_broken_bundle(monkeypatch, tmp_path):
    broken = tmp_path / "kaputt.pem"
    broken.write_text("kein Zertifikat")
    monkeypatch.setattr(updater, "CA_BUNDLES", (str(broken),))
    assert updater.ssl_context().verify_mode == ssl.CERT_REQUIRED
