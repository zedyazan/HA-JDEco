"""JDECo wire-format crypto: AES-256-GCM + RSA-2048/PKCS1v15."""
from __future__ import annotations
import base64, json, os
from xml.etree import ElementTree

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def rsa_private_key_to_pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode("ascii")


def rsa_private_key_from_pem(pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.strip().encode("ascii"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("Expected RSA private key")
    return key


def build_bootstrap_server_key(modulus_b64: str) -> rsa.RSAPublicKey:
    n = int.from_bytes(base64.b64decode(modulus_b64), "big")
    return RSAPublicNumbers(65537, n).public_key()


def rsa_public_key_to_dotnet_xml(pub: rsa.RSAPublicKey) -> str:
    """Serialize to .NET RSAKeyValue XML (f7.g.s() confirmed format)."""
    nums = pub.public_numbers()
    n_b64 = base64.b64encode(nums.n.to_bytes((nums.n.bit_length()+7)//8, "big").lstrip(b"\x00")).decode()
    e_b64 = base64.b64encode(nums.e.to_bytes((nums.e.bit_length()+7)//8, "big").lstrip(b"\x00")).decode()
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f"<RSAKeyValue><Modulus>{n_b64}</Modulus><Exponent>{e_b64}</Exponent></RSAKeyValue>")


def rsa_public_key_from_dotnet_xml(xml: str) -> rsa.RSAPublicKey:
    s = xml.strip()
    if s.startswith("<?xml"):
        s = s[s.index("?>")+2:].strip()
    root = ElementTree.fromstring(s)
    n_node = root.find("Modulus")
    if n_node is None or not n_node.text:
        raise ValueError("Missing Modulus in RSA XML")
    n = int.from_bytes(base64.b64decode(n_node.text.strip()), "big")
    return RSAPublicNumbers(65537, n).public_key()


def aes_gcm_encrypt(plaintext: str, key: bytes) -> str:
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(iv + ct).decode("ascii")


def aes_gcm_decrypt(b64_blob: str, key: bytes) -> str:
    blob = base64.b64decode(b64_blob)
    return AESGCM(key).decrypt(blob[:12], blob[12:], None).decode("utf-8")


def encrypt_request(plain_json: str, server_pub: rsa.RSAPublicKey, devid: str) -> str:
    """Build JDECo wire-format HTTP body (x0.b() confirmed format)."""
    aes_key  = os.urandom(32)
    body_b64 = aes_gcm_encrypt(plain_json, aes_key)
    aes_b64  = base64.b64encode(aes_key).decode("ascii")
    rsa_b64  = base64.b64encode(server_pub.encrypt(aes_b64.encode("utf-8"), padding.PKCS1v15())).decode("ascii")
    devid_pad = devid.rjust(24).replace(" ", ";")
    data = body_b64[:20] + devid_pad + rsa_b64 + body_b64[20:]
    return '{"data":"' + data + '\\n"}'


def decrypt_response(raw: str, client_priv: rsa.RSAPrivateKey) -> str:
    """Decrypt JDECo server response (no devid slot in response)."""
    s = raw.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            if "data" in obj:
                dv = obj["data"]
                if dv.endswith(r"\n"):
                    dv = dv[:-2]
                s = dv.rstrip("\r\n").strip()
            else:
                return s
        except (json.JSONDecodeError, KeyError):
            pass
    if len(s) < 364:
        raise ValueError(f"Response too short ({len(s)}): {s[:100]}")
    aes_key = base64.b64decode(client_priv.decrypt(base64.b64decode(s[20:364]), padding.PKCS1v15()))
    return aes_gcm_decrypt(s[:20] + s[364:], aes_key)
