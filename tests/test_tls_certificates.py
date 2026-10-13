"""Check portable roots, explicit CA files and real TLS rejection."""

import os
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import certifi

import tls_certificates


def test_missing_system_roots_use_the_bundled_certificate_file():
    with mock.patch.dict(os.environ, {"SSL_CERT_DIR": "/nonexistent-breakblocks-certificates"}):
        os.environ.pop("SSL_CERT_FILE", None)
        bundle = tls_certificates.configure_certificates()
        assert bundle == pathlib.Path(certifi.where())
        assert bundle.is_file()
        context = ssl.create_default_context()
        assert context.cert_store_stats()["x509_ca"] > 50
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_an_explicit_ca_file_is_preserved():
    with mock.patch.dict(os.environ, {"SSL_CERT_FILE": "/chosen/custom-ca.pem"}):
        assert tls_certificates.configure_certificates() == pathlib.Path("/chosen/custom-ca.pem")
        assert os.environ["SSL_CERT_FILE"] == "/chosen/custom-ca.pem"


def test_missing_bundle_is_reported():
    with (
        mock.patch.dict(os.environ),
        mock.patch.object(certifi, "where", return_value="/missing/cacert.pem"),
    ):
        os.environ.pop("SSL_CERT_FILE", None)
        try:
            tls_certificates.configure_certificates()
        except RuntimeError as error:
            assert "certificate bundle is missing" in str(error)
        else:
            raise AssertionError("A missing certificate bundle was accepted")


def test_untrusted_servers_are_rejected_and_explicit_local_ca_works():
    executable = shutil.which("openssl")
    if not executable:
        print("Skipped local self-signed TLS check (OpenSSL command unavailable)")
        return
    with tempfile.TemporaryDirectory(prefix="breakblocks-tls-test-") as temporary:
        folder = pathlib.Path(temporary)
        certificate, key = folder / "certificate.pem", folder / "key.pem"
        subprocess.run(
            [
                executable,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"verified")

            def log_message(self, *_arguments):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate, key)
        server.socket = server_context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.dict(os.environ, {"SSL_CERT_DIR": str(folder / "no-system-roots")}):
                os.environ.pop("SSL_CERT_FILE", None)
                tls_certificates.configure_certificates()
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                url = f"https://localhost:{server.server_port}/"
                try:
                    opener.open(url, timeout=5)
                except urllib.error.URLError as error:
                    assert isinstance(error.reason, ssl.SSLCertVerificationError)
                else:
                    raise AssertionError("An untrusted server certificate was accepted")

                os.environ["SSL_CERT_FILE"] = str(certificate)
                tls_certificates.configure_certificates()
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(url, timeout=5) as response:
                    assert response.read() == b"verified"
                try:
                    opener.open(f"https://127.0.0.1:{server.server_port}/", timeout=5)
                except urllib.error.URLError as error:
                    assert isinstance(error.reason, ssl.SSLCertVerificationError)
                else:
                    raise AssertionError("A certificate for the wrong hostname was accepted")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} certificate checks")
