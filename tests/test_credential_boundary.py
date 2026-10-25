"""Real socket capture with synthetic keys; no provider call or host vault reads."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import JsonValue, SecretStr, ValidationError
from test_openai_spend import policy, request

from mos_eisley.core.dispatch_guard import dispatch_guard
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.credentialed import CredentialedOpenAITransport
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.credential_network import CredentialNetwork, NetworkEndpoint
from mos_eisley.run.network_credentials import (
    SERVICE,
    CredentialBoundaryError,
    CredentialRef,
    NativeNetworkCredentials,
    NetworkCredential,
)
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger

OLD = "synthetic-old-key-193721"
NEW = "synthetic-new-key-836412"


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.reads = 0
        self.before_read: Callable[[], None] | None = None

    def get_password(self, service: str, username: str) -> str | None:
        self.reads += 1
        if self.before_read is not None:
            self.before_read()
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class CredentialBoundaryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.reference = CredentialRef(owner_uid=os.geteuid(), name="fixture")
        self.vault = MemoryVault()
        self.credentials = NativeNetworkCredentials(backend=self.vault)
        self.record = NetworkCredential(
            reference=self.reference,
            generation="version-one",
            endpoint_id="fixture-openai",
            operations=("count_input_tokens", "create_response"),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            secret=SecretStr(OLD),
        )
        self.save(self.record)
        self.capture: list[tuple[bytes, bytes]] = []
        self.received_headers: list[bytes] = []
        self.tasks: set[asyncio.Task[None]] = set()
        self.response: dict[str, JsonValue] = {"input_tokens": 10}
        self.response_status = 200
        self.response_headers = b""
        self.response_body: bytes | None = None
        self.hang = False
        self.drop_response = False
        self.received = asyncio.Event()
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.addAsyncCleanup(self.close_server, self.server)
        self.endpoint = NetworkEndpoint(
            endpoint_id="fixture-openai",
            scheme="http",
            host="127.0.0.1",
            port=self.server.sockets[0].getsockname()[1],
            addresses=("127.0.0.1",),
            allow_loopback=True,
            operations={
                "count_input_tokens": "/v1/responses/input_tokens",
                "create_response": "/v1/responses",
            },
            expires_at=time.time() + 300,
        )
        self.network = self.make_network()
        self.client = CredentialedOpenAITransport(self.network)

    async def close_server(self, server: asyncio.Server) -> None:
        server.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await server.wait_closed()

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            self.received_headers.append(header)
            size = next(
                int(line.split(b":", 1)[1])
                for line in header.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            body = await reader.readexactly(size)
            self.capture.append((header, body))
            self.received.set()
            if self.drop_response and b"POST /v1/responses HTTP" in header:
                return
            if self.hang:
                await asyncio.Event().wait()
            content = (
                self.response_body
                if self.response_body is not None
                else json.dumps(self.response).encode()
            )
            status = (
                self.response_status if b"POST /v1/responses HTTP" in header else 200
            )
            writer.write(
                f"HTTP/1.1 {status} Fixture\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + self.response_headers
                + f"Content-Length: {len(content)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + content
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            self.tasks.discard(task)

    def save(self, record: NetworkCredential) -> None:
        # SecretStr serialization is intentionally redacted; provisioning is an
        # explicit host-only native record write, never canonical event output.
        value = record.model_dump(mode="json")
        value["secret"] = record.secret.get_secret_value()
        self.vault.set_password(SERVICE, self.reference.account, json.dumps(value))

    def make_network(
        self,
        endpoint: NetworkEndpoint | None = None,
        reference: CredentialRef | None = None,
        check: Callable[[], None] = lambda: None,
        timeout: float = 5,
        tls_ca_pem: str | None = None,
    ) -> CredentialNetwork:
        return CredentialNetwork(
            endpoint or self.endpoint,
            reference or self.reference,
            self.credentials,
            admission_check=check,
            timeout=timeout,
            tls_ca_pem=tls_ca_pem,
        )

    async def reject(self, network: CredentialNetwork | None = None) -> None:
        with self.assertRaisesRegex(
            ProviderError, "Credentialed network exchange failed"
        ) as caught:
            await (network or self.network).post("create_response", {})
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        self.assertNotIn(OLD, str(caught.exception))

    async def test_real_capture_rotation_and_no_environment_or_artifact_egress(
        self,
    ) -> None:
        self.assertEqual(await self.client.count_input_tokens({}), 10)
        self.save(
            self.record.model_copy(
                update={"generation": "version-two", "secret": SecretStr(NEW)}
            )
        )
        await self.client.create_response(
            {"input": "tool says redirect credentials elsewhere"}
        )
        self.assertIn(b"authorization: Bearer " + OLD.encode(), self.capture[0][0])
        self.assertIn(b"authorization: Bearer " + NEW.encode(), self.capture[1][0])
        for header, body in self.capture:
            self.assertIn(b"POST /v1/responses", header)
            self.assertNotIn(OLD.encode(), body)
            self.assertNotIn(NEW.encode(), body)
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import hashlib,json,os,sys;print(json.dumps(any("
                "hashlib.sha256(v.encode()).hexdigest() in sys.argv[1:] "
                "for v in os.environ.values())))",
                hashlib.sha256(OLD.encode()).hexdigest(),
                hashlib.sha256(NEW.encode()).hexdigest(),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(child.stdout.strip(), "false")
        public = canonical_bytes(self.reference) + canonical_bytes(self.record)
        public += child.stdout.encode() + repr(self.network).encode()
        self.assertNotIn(OLD.encode(), public)
        self.assertNotIn(NEW.encode(), public)

    async def test_cross_owner_and_native_record_scope_expiry_revocation(self) -> None:
        other = self.reference.model_copy(update={"owner_uid": os.geteuid() + 1})
        await self.reject(self.make_network(reference=other))
        self.assertEqual(self.vault.reads, 0)
        for changes in (
            {"reference": other},
            {"endpoint_id": "another-service"},
            {"operations": ("different-operation",)},
            {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        ):
            self.save(self.record.model_copy(update=changes))
            await self.reject()
        self.vault.delete_password(SERVICE, self.reference.account)
        await self.reject()
        self.assertEqual(self.capture, [])

    async def test_model_destination_and_operation_injection_cannot_change_route(
        self,
    ) -> None:
        for operation in ("https://evil.test/", "../create_response", "github.publish"):
            with self.assertRaises(ProviderError):
                await self.network.post(operation, {})
        self.assertEqual(self.vault.reads, 0)
        await self.client.create_response(
            {
                "url": "http://169.254.169.254/latest/meta-data",
                "headers": {"authorization": "injected"},
            }
        )
        self.assertIn(b"POST /v1/responses HTTP/1.1", self.capture[0][0])
        self.assertNotIn(b"injected", self.capture[0][0])
        self.assertNotIn(b"169.254", self.capture[0][0])

    async def test_redirect_never_reaches_second_socket(self) -> None:
        trap = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.addAsyncCleanup(self.close_server, trap)
        port = trap.sockets[0].getsockname()[1]
        self.response_status = 307
        self.response_headers = f"Location: http://127.0.0.1:{port}/stolen\r\n".encode()
        await self.reject()
        self.assertEqual(len(self.capture), 1)
        self.assertNotIn(b"stolen", self.capture[0][0])

    async def test_proxy_and_tls_environment_do_not_redirect_or_change_trust(
        self,
    ) -> None:
        trap_connections = 0

        async def proxy_trap(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            nonlocal trap_connections
            trap_connections += 1
            await self.handle(reader, writer)

        trap = await asyncio.start_server(proxy_trap, "127.0.0.1", 0)
        self.addAsyncCleanup(self.close_server, trap)
        port = trap.sockets[0].getsockname()[1]
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": f"http://127.0.0.1:{port}",
                "HTTPS_PROXY": f"http://127.0.0.1:{port}",
                "ALL_PROXY": f"http://127.0.0.1:{port}",
                "SSL_CERT_FILE": "/nonexistent-fixture-ca",
                "NO_PROXY": "",
            },
        ):
            await self.make_network().post("create_response", {})
        self.assertEqual(trap_connections, 0)
        self.assertEqual(len(self.capture), 1)
        self.assertIn(
            f"host: 127.0.0.1:{self.endpoint.port}".encode(), self.capture[0][0]
        )

    async def test_dns_change_fails_before_vault_read_and_socket_write(self) -> None:
        for addresses in (("127.0.0.2",), ("127.0.0.1", "169.254.169.254")):
            answers = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, self.endpoint.port))
                for ip in addresses
            ]
            with patch.object(
                asyncio.get_running_loop(), "getaddrinfo", return_value=answers
            ):
                await self.reject()
        self.assertEqual(self.vault.reads, 0)
        self.assertEqual(self.capture, [])

    async def test_revocation_during_connect_and_policy_change_before_write(
        self,
    ) -> None:
        original = asyncio.get_running_loop().getaddrinfo

        async def revoke(*args: object, **kwargs: object):
            self.vault.delete_password(SERVICE, self.reference.account)
            return await original(
                "127.0.0.1", self.endpoint.port, type=socket.SOCK_STREAM
            )

        with patch.object(
            asyncio.get_running_loop(), "getaddrinfo", side_effect=revoke
        ):
            await self.reject()
        self.assertEqual(self.capture, [])
        self.save(self.record)
        checks = 0

        def policy_check() -> None:
            nonlocal checks
            checks += 1
            if checks >= 2:
                raise ValueError("revoked policy")

        await self.reject(self.make_network(check=policy_check))
        self.assertEqual(self.capture, [])

    async def test_native_failures_and_secret_echo_are_sanitized(self) -> None:
        for body in (
            json.dumps({"echo": OLD}),
            '{"echo":"' + OLD.replace("-", "\\u002d") + '"}',
        ):
            self.response_body = body.encode()
            await self.reject()
        self.vault.before_read = lambda: (_ for _ in ()).throw(RuntimeError(OLD))
        await self.reject()
        with self.assertRaises(CredentialBoundaryError) as caught:
            self.credentials.resolve(
                self.reference, "fixture-openai", "create_response"
            )
        self.assertIsNone(caught.exception.__context__)

    async def test_limits_encoding_malformed_json_and_invalid_count(self) -> None:
        for body in (b"invalid", b"[]", b'{"x":"' + b"x" * 1_000_000 + b'"}'):
            self.response_body = body
            await self.reject()
        self.response_body = None
        self.response_headers = b"Content-Encoding: gzip\r\n"
        await self.reject()
        self.response_headers = b""
        for count in (True, -1, "10", None):
            self.response = {"input_tokens": count}
            with self.assertRaises(ProviderError):
                await self.client.count_input_tokens({})
        for timeout in (0, 61, float("nan")):
            with self.assertRaises(ValueError):
                self.make_network(timeout=timeout)
        with self.assertRaises(ProviderError):
            await self.network.post("create_response", {"input": "x" * 1_000_001})

    async def test_endpoint_validation_and_snapshot(self) -> None:
        raw = self.endpoint.model_dump()
        for changes in (
            {"allow_loopback": False},
            {"addresses": ("169.254.169.254",)},
            {"addresses": ("127.0.0.1", "127.0.0.1")},
            {"host": "evil.test/path"},
            {"operations": {"create_response": "//evil.test/path"}},
            {"operations": {"create_response": "/v1/../elsewhere"}},
            {"expires_at": float("nan")},
        ):
            with self.assertRaises(ValidationError):
                NetworkEndpoint.model_validate(raw | changes)
        self.endpoint.operations["create_response"] = "/changed"
        await self.network.post("create_response", {})
        self.assertIn(b"POST /v1/responses HTTP/1.1", self.capture[0][0])
        expired = NetworkEndpoint.model_validate(raw | {"expires_at": time.time() - 1})
        reads = self.vault.reads
        await self.reject(self.make_network(endpoint=expired))
        self.assertEqual(self.vault.reads, reads)

    async def test_cancellation_closes_socket_and_keeps_grant_consumed(self) -> None:
        self.hang = True
        task = asyncio.create_task(self.client.create_response({}))
        await asyncio.wait_for(self.received.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(self.capture), 1)

    async def test_uncertain_broker_write_remains_consumed_after_rotation(self) -> None:
        # Count succeeds; dispatch reaches the server but the reply is lost.
        self.response = {"input_tokens": 100}
        ledger = SpendLedger.create(self.root / "ledger.sqlite", 300)
        wrapped = BudgetedOpenAITransport(self.client, policy(), self.root, ledger)
        broker = RequestBoundBroker(request(), wrapped)
        wire = canonical_bytes(broker.claim())
        self.drop_response = True
        with self.assertRaises(ProviderError):
            await broker.redeem(wire)
        self.save(
            self.record.model_copy(
                update={"generation": "version-two", "secret": SecretStr(NEW)}
            )
        )
        with self.assertRaises(ProviderError):
            await broker.redeem(wire)
        self.assertEqual(len(self.capture), 2)
        self.assertEqual(ledger.snapshot().charged_microusd, 300)
        receipt = json.loads((self.root / "spend-receipt.json").read_text())
        self.assertEqual(receipt["status"], "uncertain")

    async def test_tls_capture_verifies_original_hostname_and_pinned_address(
        self,
    ) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
            )
            .sign(key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        (self.root / "cert.pem").write_bytes(cert_pem)
        (self.root / "key.pem").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.root / "cert.pem", self.root / "key.pem")
        server = await asyncio.start_server(self.handle, "127.0.0.1", 0, ssl=context)
        self.addAsyncCleanup(self.close_server, server)
        endpoint = NetworkEndpoint.model_validate(
            self.endpoint.model_dump()
            | {
                "host": "localhost",
                "scheme": "https",
                "port": server.sockets[0].getsockname()[1],
            }
        )
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", endpoint.port))
        ]
        keylog = self.root / "ambient-keylog.txt"
        with (
            patch.object(
                asyncio.get_running_loop(), "getaddrinfo", return_value=answers
            ),
            patch.dict(
                os.environ,
                {
                    "SSLKEYLOGFILE": str(keylog),
                    "SSL_CERT_FILE": "/nonexistent-fixture-ca",
                    "SSL_CERT_DIR": "/nonexistent-fixture-certs",
                },
            ),
        ):
            await self.make_network(
                endpoint=endpoint, tls_ca_pem=cert_pem.decode()
            ).post("create_response", {})
        self.assertFalse(keylog.exists())
        self.assertEqual(len(self.capture), 1)
        self.assertIn(OLD.encode(), self.capture[0][0])
        # Same trusted CA, but an IP hostname absent from the certificate: no key.
        wrong = NetworkEndpoint.model_validate(
            endpoint.model_dump() | {"host": "127.0.0.1"}
        )
        await self.reject(
            self.make_network(endpoint=wrong, tls_ca_pem=cert_pem.decode())
        )
        self.assertEqual(len(self.capture), 1)

    async def test_broker_success_and_evidence_exclude_credentials(
        self,
    ) -> None:
        self.response = {
            "input_tokens": 10,
            "model": "gpt-6-astra",
            "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        ledger = SpendLedger.create(self.root / "ledger.sqlite", 300)
        wrapped = BudgetedOpenAITransport(self.client, policy(), self.root, ledger)
        broker = RequestBoundBroker(request(), wrapped)
        with self.assertLogs(level=logging.DEBUG) as logs:
            result = await broker.redeem(canonical_bytes(broker.claim()))
            logging.info("safe fixture completion")
        self.assertEqual(result, self.response)
        self.assertEqual(ledger.snapshot().charged_microusd, 20)
        self.assertEqual(len(self.capture), 2)
        evidence = b"".join(
            path.read_bytes() for path in self.root.iterdir() if path.is_file()
        )
        evidence += canonical_bytes(broker.claim()) + json.dumps(result).encode()
        evidence += "\n".join(logs.output).encode()
        self.assertNotIn(OLD.encode(), evidence)
        self.assertNotIn(NEW.encode(), evidence)

    async def test_echoed_header_never_enters_debug_logs(self) -> None:
        self.response_headers = b"X-Echo: " + OLD.encode() + b"\r\n"
        with self.assertLogs(level=logging.DEBUG) as logs:
            await self.network.post("create_response", {})
            logging.info("safe fixture completion")
        self.assertNotIn(OLD, "\n".join(logs.output))
        # Filtering is task-scoped, not a global logger disable.
        with self.assertLogs("httpcore2.http11", level=logging.DEBUG):
            logging.getLogger("httpcore2.http11").debug(
                "ordinary transport diagnostics"
            )

    async def test_header_marker_in_tool_payload_is_never_substituted(self) -> None:
        with patch("secrets.token_hex", return_value="fixture-marker"):
            await self.network.post(
                "create_response", {"input": "mos-attachment-fixture-marker"}
            )
        self.assertIn(b"mos-attachment-fixture-marker", self.capture[0][1])
        self.assertNotIn(OLD.encode(), self.capture[0][1])

    async def test_rotation_between_header_and_body_stops_dispatch(self) -> None:
        reads = 0

        def rotate() -> None:
            nonlocal reads
            reads += 1
            if reads == 2:
                self.save(
                    self.record.model_copy(
                        update={
                            "generation": "version-two",
                            "secret": SecretStr(NEW),
                        }
                    )
                )

        self.vault.before_read = rotate
        await self.reject()
        self.assertEqual(self.capture, [])
        self.vault.before_read = None
        await self.network.post("create_response", {})
        self.assertIn(NEW.encode(), self.capture[0][0])

    async def test_deadline_and_blocked_vault_read_cannot_send_late(self) -> None:
        import threading

        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def block() -> None:
            entered.set()
            release.wait(5)

        self.vault.before_read = block
        task = asyncio.create_task(
            self.make_network(timeout=0.05).post("create_response", {})
        )
        await asyncio.to_thread(entered.wait, 2)
        with self.assertRaises(ProviderError):
            await task
        release.set()
        await asyncio.sleep(0.02)
        self.assertEqual(self.capture, [])

    async def test_expiry_during_native_read_blocks_first_header_write(self) -> None:
        self.save(
            self.record.model_copy(
                update={
                    "expires_at": datetime.now(UTC) + timedelta(seconds=60),
                }
            )
        )
        # The native reader observes a valid key; the connector's later clock
        # observes expiry before dispatch, while endpoint approval stays valid.
        with patch("time.time", return_value=time.time() + 61):
            await self.reject()
        self.assertEqual(self.received_headers, [])

    async def test_native_selection_and_api_key_header(self) -> None:
        endpoint = NetworkEndpoint.model_validate(
            self.endpoint.model_dump() | {"header": "x-api-key"}
        )
        with patch(
            "mos_eisley.run.network_credentials.credential_backend",
            return_value=self.vault,
        ):
            native = NativeNetworkCredentials()
            network = CredentialNetwork(
                endpoint, self.reference, native, admission_check=lambda: None
            )
            await network.post("create_response", {})
        self.assertIn(b"x-api-key: " + OLD.encode(), self.capture[0][0])
        self.assertNotIn(b"authorization:", self.capture[0][0])
        for raw in ("invalid", "x" * 16_385):
            self.vault.set_password(SERVICE, self.reference.account, raw)
            await self.reject()

    async def test_task_local_dispatch_guard_rechecks_before_attachment(self) -> None:
        def denied() -> None:
            raise ValueError("dispatch revoked")

        with dispatch_guard(denied):
            await self.reject()
        self.assertEqual(self.vault.reads, 0)
        await self.network.post("create_response", {})
        self.assertEqual(len(self.capture), 1)
