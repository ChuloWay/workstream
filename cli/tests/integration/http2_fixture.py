"""A loopback TLS peer that receives a body, then sends graceful HTTP/2 GOAWAY.

Only the frames needed for this transport regression are implemented. There is
no application handler or HTTP client replacement: the built CLI negotiates
TLS/HTTP2, writes its request, and decides whether to replay on a new connection.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import socket
import ssl
from threading import Event, Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"


def receive(connection, size):
    value = bytearray()
    while len(value) < size:
        chunk = connection.recv(size - len(value))
        if not chunk:
            raise EOFError
        value.extend(chunk)
    return bytes(value)


def send_frame(connection, kind, flags=0, stream=0, payload=b""):
    connection.sendall(
        len(payload).to_bytes(3, "big")
        + bytes((kind, flags))
        + stream.to_bytes(4, "big")
        + payload
    )


def receive_request(connection):
    assert connection.selected_alpn_protocol() == "h2"
    assert receive(connection, len(PREFACE)) == PREFACE
    send_frame(connection, 4)  # SETTINGS
    stream_id = None
    body = bytearray()
    while True:
        header = receive(connection, 9)
        length = int.from_bytes(header[:3], "big")
        kind, flags = header[3:5]
        stream = int.from_bytes(header[5:], "big") & 0x7FFFFFFF
        assert length <= 16384
        payload = receive(connection, length)
        if kind == 4 and not flags & 1:
            send_frame(connection, 4, 1)  # SETTINGS ACK
        elif kind == 1:  # HEADERS: no HPACK decoding is needed to count requests.
            assert stream_id is None and stream > 0 and flags & 4
            stream_id = stream
            assert not flags & 1  # These writes must carry their nonempty JSON body.
        elif kind == 0:
            assert stream == stream_id and not flags & 8  # No padded DATA.
            body.extend(payload)
            assert len(body) <= 8192
            if flags & 1:  # END_STREAM: the complete body reached the peer.
                return bytes(body)


@contextmanager
def goaway_fixture(tmp_path):
    """Observe every fresh TLS connection until the built CLI exits."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CLI test loopback")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "peer.pem", tmp_path / "peer-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    context.set_alpn_protocols(["h2"])
    stopped = Event()
    bodies, connections, errors = [], [], []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)

    def serve():
        while not stopped.is_set():
            try:
                raw, _address = listener.accept()
            except TimeoutError:
                continue
            try:
                raw.settimeout(3)
                with raw, context.wrap_socket(raw, server_side=True) as connection:
                    connections.append(connection.selected_alpn_protocol())
                    bodies.append(receive_request(connection))
                    # last_stream_id=0, NO_ERROR: none of the streams is reported
                    # processed. A rewindable request is retried by Go here.
                    if len(bodies) > 1:
                        # A replay is already observable. Close without another
                        # GOAWAY so the broken client cannot loop until timeout.
                        continue
                    send_frame(connection, 7, payload=b"\x00" * 8)
                    # Let the client process GOAWAY before closing the TLS peer.
                    try:
                        while connection.recv(4096):
                            pass
                    except (TimeoutError, ConnectionResetError):
                        pass
            except Exception as error:  # Surface fixture failures to the main test.
                errors.append(error)
                stopped.set()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield (
            f"https://127.0.0.1:{listener.getsockname()[1]}",
            {"SSL_CERT_FILE": str(cert_path)},
            bodies,
            connections,
        )
    finally:
        stopped.set()
        thread.join(timeout=4)
        listener.close()
        assert not thread.is_alive(), "HTTP/2 fixture did not terminate"
        assert not errors, errors
