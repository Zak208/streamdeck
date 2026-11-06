"""
SSL / TLS certificate management for StreamDesk.

Generates and manages a local Root Certificate Authority (CA) and a Server
Certificate signed by this CA, enabling HTTPS on local networks for PWA
installation in Chrome and mobile browsers.
"""

import datetime
import ipaddress
import os
import socket
import threading
from typing import List, Optional, Set, Tuple

import psutil

from server.paths import CONFIG_DIR

CERT_FILE = os.path.join(CONFIG_DIR, "cert.pem")
KEY_FILE = os.path.join(CONFIG_DIR, "key.pem")
CA_CERT_FILE = os.path.join(CONFIG_DIR, "ca.crt")
CA_KEY_FILE = os.path.join(CONFIG_DIR, "ca.key")

_lock = threading.Lock()


def get_all_local_ips() -> Set[str]:
    """Collects all usable IPv4 addresses on the host machine to include in SAN."""
    ips = {"127.0.0.1", "0.0.0.0"}
    try:
        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if not ip.startswith("169.254."):
                        ips.add(ip)
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("169.254."):
                ips.add(ip)
    except Exception:
        pass

    return ips


def get_ca_certificate_path() -> Optional[str]:
    """Returns path to the Root CA certificate file if it exists."""
    return CA_CERT_FILE if os.path.exists(CA_CERT_FILE) else None


def ensure_ssl_certificates(preferred_ip: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Ensures a valid Root CA and Server TLS Certificate exist in CONFIG_DIR.

    Returns:
        (cert_path, key_path) if available and valid, or (None, None) if generation fails.
    """
    with _lock:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)

            # If certificates already exist, verify they exist and are non-empty
            if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
                if os.path.getsize(CERT_FILE) > 0 and os.path.getsize(KEY_FILE) > 0:
                    return CERT_FILE, KEY_FILE

            # Generate new Root CA and Server certificates
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

            # 1. Root Certificate Authority (CA)
            ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            ca_name = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "StreamDesk Pro"),
                x509.NameAttribute(NameOID.COMMON_NAME, "StreamDesk Root CA"),
            ])
            now = datetime.datetime.now(datetime.timezone.utc)
            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(ca_name)
                .issuer_name(ca_name)
                .public_key(ca_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_cert_sign=True,
                        crl_sign=True,
                        key_encipherment=False,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .sign(ca_key, hashes.SHA256())
            )

            # Save Root CA files
            with open(CA_KEY_FILE, "wb") as f:
                f.write(
                    ca_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
            with open(CA_CERT_FILE, "wb") as f:
                f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

            # 2. Server Certificate
            server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            server_name = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "StreamDesk Pro"),
                x509.NameAttribute(NameOID.COMMON_NAME, "StreamDesk Server"),
            ])

            # Subject Alternative Names (SAN)
            san_entries: List[x509.GeneralName] = [
                x509.DNSName("localhost"),
                x509.DNSName("streamdesk.local"),
            ]
            all_ips = get_all_local_ips()
            if preferred_ip:
                all_ips.add(preferred_ip)

            for ip_str in sorted(all_ips):
                try:
                    san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
                except ValueError:
                    pass

            server_cert = (
                x509.CertificateBuilder()
                .subject_name(server_name)
                .issuer_name(ca_name)
                .public_key(server_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_encipherment=True,
                        key_cert_sign=False,
                        crl_sign=False,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([
                        ExtendedKeyUsageOID.SERVER_AUTH,
                        ExtendedKeyUsageOID.CLIENT_AUTH,
                    ]),
                    critical=False,
                )
                .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
                .sign(ca_key, hashes.SHA256())
            )

            # Save Server Certificate & Private Key
            with open(KEY_FILE, "wb") as f:
                f.write(
                    server_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
            with open(CERT_FILE, "wb") as f:
                f.write(server_cert.public_bytes(serialization.Encoding.PEM))

            return CERT_FILE, KEY_FILE

        except Exception as exc:
            print(f"[SSL] Error initializing SSL certificates: {exc}")
            return None, None
