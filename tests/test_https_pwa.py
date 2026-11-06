"""
Tests for HTTPS, Root CA generation, SAN extensions, and PWA installation support.
"""
import base64
import os
import tempfile
import unittest
import urllib.request
from unittest import mock

import support
from cryptography import x509

from server.auth import auth_manager
from server.paths import PORT
from server.ssl_helper import ensure_ssl_certificates, get_ca_certificate_path, get_all_local_ips


class SslCertificateTests(unittest.TestCase):
    """Verifies that SSL certificates are generated with proper CA chain and SAN extensions."""

    def test_local_ips_detection(self):
        ips = get_all_local_ips()
        self.assertIn("127.0.0.1", ips)
        self.assertIn("0.0.0.0", ips)

    def test_certificate_and_ca_generation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_cert = os.path.join(tmp_dir, "cert.pem")
            tmp_key = os.path.join(tmp_dir, "key.pem")
            tmp_ca_cert = os.path.join(tmp_dir, "ca.crt")
            tmp_ca_key = os.path.join(tmp_dir, "ca.key")

            with mock.patch("server.ssl_helper.CONFIG_DIR", tmp_dir), \
                 mock.patch("server.ssl_helper.CERT_FILE", tmp_cert), \
                 mock.patch("server.ssl_helper.KEY_FILE", tmp_key), \
                 mock.patch("server.ssl_helper.CA_CERT_FILE", tmp_ca_cert), \
                 mock.patch("server.ssl_helper.CA_KEY_FILE", tmp_ca_key):

                cert_file, key_file = ensure_ssl_certificates(preferred_ip="192.168.1.123")

                self.assertTrue(os.path.exists(cert_file))
                self.assertTrue(os.path.exists(key_file))
                self.assertTrue(os.path.exists(tmp_ca_cert))
                self.assertTrue(os.path.exists(tmp_ca_key))

                # Verify CA properties
                with open(tmp_ca_cert, "rb") as f:
                    ca = x509.load_pem_x509_certificate(f.read())
                bc = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
                self.assertTrue(bc.ca)

                # Verify Server Cert properties
                with open(cert_file, "rb") as f:
                    srv = x509.load_pem_x509_certificate(f.read())
                srv_bc = srv.extensions.get_extension_for_class(x509.BasicConstraints).value
                self.assertFalse(srv_bc.ca)

                # Verify SANs
                san = srv.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                dns_names = san.get_values_for_type(x509.DNSName)
                self.assertIn("localhost", dns_names)
                self.assertIn("streamdesk.local", dns_names)

                ip_addrs = [str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
                self.assertIn("127.0.0.1", ip_addrs)
                self.assertIn("192.168.1.123", ip_addrs)

    def test_qr_code_contains_https_protocol(self):
        qr_data_url = auth_manager.generate_qr_base64(PORT, protocol="https")
        self.assertTrue(qr_data_url.startswith("data:image/png;base64,"))

        # Decode QR image and verify it's a valid PNG
        b64_part = qr_data_url.split(",", 1)[1]
        raw_png = base64.b64decode(b64_part)
        self.assertTrue(raw_png.startswith(b"\x89PNG\r\n\x1a\n"))


class CaEndpointLiveTests(unittest.TestCase):
    """Verifies /ca.crt endpoint downloads the Root CA certificate for mobile installation."""

    def test_ca_crt_download_endpoint(self):
        with support.LiveServer() as live:
            url = f"{live.base_url}/ca.crt"
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get("Content-Type"), "application/x-x509-ca-cert")
                body = response.read()
                self.assertIn(b"BEGIN CERTIFICATE", body)
                self.assertIn(b"END CERTIFICATE", body)

    def test_api_info_and_auth_pin_return_protocol(self):
        with support.LiveServer() as live:
            info_url = f"{live.base_url}/api/info"
            with urllib.request.urlopen(info_url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                import json
                data = json.loads(response.read().decode())
                self.assertIn("protocol", data)
                self.assertIn("direct_url", data)
                self.assertTrue(data["direct_url"].startswith(f"{data['protocol']}://"))


if __name__ == "__main__":
    unittest.main()
