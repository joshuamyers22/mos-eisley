"""Remote MCP permissions, wire limits, DNS, credentials and real TLS tests."""

import asyncio
import contextlib
import io
import ipaddress
import json
import os
import socket
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpcore2
import httpx2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fixtures.mcp_http_server import MCPHTTPFixture

from mos_eisley.cli import main
from mos_eisley.core.protocol import ToolCallBlock
from mos_eisley.tools.mcp import MCPConfig, MCPFailure, connect_mcp
from mos_eisley.tools.mcp_http import (
    MCPHTTPError,
    MCPHTTPSettings,
    MCPHTTPTransport,
    PinnedMCPBackend,
)


def remote(url: str, **changes: Any) -> MCPConfig:
    return MCPConfig(
        transport="streamable_http",
        http=MCPHTTPSettings.model_validate(
            {
                "url": url,
                "authentication": "bearer",
                "token_env": "MCP_FIXTURE_TOKEN",
                "token_owner_uid": os.geteuid(),
                "allow_loopback_http": url.startswith("http:"),
                **changes,
            }
        ),
        tools={"read_value": "read", "write_value": "write", "slow": "read"},
        allow_writes=True,
        timeout_seconds=2,
    )


def call(name: str, **args: Any) -> ToolCallBlock:
    return ToolCallBlock(id="remote-" + name, name=name, args=args)


class HTTPPolicyTests(TestCase):
    def test_strict_configuration(self) -> None:
        for changes in (
            {"url": "http://example.com/mcp"},
            {"url": "https://u:secret@example.com/mcp"},
            {"url": "https://example.com/mcp?token=secret"},
            {"url": "https://example.com/mcp#fragment"},
            {"url": "https://[malformed/mcp"},
            {"url": "file:///mcp"},
            {"authentication": "bearer"},
            {"private_networks": ("0.0.0.0/0",)},
            {"private_networks": ("169.254.0.0/16",)},
            {"ca_file": "relative.pem"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                MCPHTTPSettings.model_validate(
                    {
                        "url": "https://example.com/mcp",
                        "authentication": "none",
                        **changes,
                    }
                )
        cfg = remote("http://127.0.0.1:1234/mcp")
        for changes in (
            {"command": "/bin/false"},
            {"env": ["TOKEN"]},
            {"http": None},
            {"allow_writes": False},
        ):
            with self.assertRaises(ValueError):
                MCPConfig.model_validate_json(
                    json.dumps({**cfg.model_dump(mode="json"), **changes})
                )

    def test_network_grants(self) -> None:
        public = MCPHTTPSettings(url="https://example.com/mcp", authentication="none")
        for address in (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.169.254",
            "::1",
            "::ffff:8.8.8.8",
            "224.0.0.1",
            "0.0.0.0",
        ):
            self.assertFalse(public.allows_address(address))
        self.assertTrue(public.allows_address("8.8.8.8"))
        scoped = public.model_copy(update={"private_networks": ("10.2.0.0/16",)})
        self.assertTrue(scoped.allows_address("10.2.3.4"))
        self.assertFalse(scoped.allows_address("10.3.3.4"))

    def test_token_owner_and_format(self) -> None:
        cfg = remote("https://example.com/mcp").http
        assert cfg is not None
        with (
            patch.dict(os.environ, {"MCP_FIXTURE_TOKEN": "fixture-A"}),
            patch("os.geteuid", return_value=os.geteuid() + 1),
            self.assertRaises(MCPHTTPError),
        ):
            cfg.token()
        for token in ("", "header\ninjection", "x" * 8193):
            with (
                patch.dict(os.environ, {"MCP_FIXTURE_TOKEN": token}),
                self.assertRaises(MCPHTTPError),
            ):
                cfg.token()


class DNSPinningTests(IsolatedAsyncioTestCase):
    async def test_dns_pins_literal_and_rejects_rebinding(self) -> None:
        settings = MCPHTTPSettings(url="https://example.com/mcp", authentication="none")
        backend = PinnedMCPBackend(settings)
        network = AsyncMock(spec=httpcore2.AsyncNetworkBackend)
        backend.backend = cast(httpcore2.AsyncNetworkBackend, network)

        def answer(ip: str) -> list[Any]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

        with patch(
            "anyio.getaddrinfo",
            new=AsyncMock(side_effect=[answer("8.8.8.8"), answer("127.0.0.1")]),
        ):
            await backend.connect_tcp("example.com", 443, timeout=1)
            with self.assertRaises(MCPHTTPError):
                await backend.connect_tcp("example.com", 443, timeout=1)
        self.assertEqual(network.connect_tcp.await_count, 1)
        self.assertEqual(network.connect_tcp.call_args.args[0], "8.8.8.8")
        with self.assertRaises(MCPHTTPError):
            await backend.connect_tcp("unapproved.invalid", 443)

    async def test_transport_rejects_other_endpoint_and_resumption_before_send(
        self,
    ) -> None:
        settings = MCPHTTPSettings(url="https://example.com/mcp", authentication="none")
        for request in (
            httpx2.Request("POST", "https://other.invalid/mcp"),
            httpx2.Request("GET", settings.url, headers={"last-event-id": "retry"}),
        ):
            async with MCPHTTPTransport(settings) as transport:
                with self.assertRaises(MCPHTTPError):
                    await transport.handle_async_request(request)


class RemoteRoundtripTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fixture = MCPHTTPFixture()
        self.fixture.start()
        self.addCleanup(self.fixture.close)
        self.token_patch = patch.dict(os.environ, {"MCP_FIXTURE_TOKEN": "fixture-A"})
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)

    async def test_real_discovery_read_write_and_denial(self) -> None:
        async with connect_mcp(remote(self.fixture.url)) as dispatcher:
            result = await dispatcher.dispatch(call("write_value", value=7))
            self.assertFalse(result.is_error)
            result = await dispatcher.dispatch(call("read_value"))
            self.assertEqual(
                json.loads(result.content)["structured_content"]["value"], 7
            )
            self.assertTrue((await dispatcher.dispatch(call("unapproved"))).is_error)
        self.assertEqual(self.fixture.writes, 1)
        self.assertTrue(
            all(token == "Bearer fixture-A" for _, token in self.fixture.requests)
        )

    async def test_streaming_responses(self) -> None:
        other = MCPHTTPFixture(sse=True)
        other.start()
        self.addCleanup(other.close)
        async with connect_mcp(remote(other.url)) as dispatcher:
            self.assertFalse((await dispatcher.dispatch(call("read_value"))).is_error)

    async def test_legacy_versions_and_unsupported_version(self) -> None:
        for version in ("2025-11-25", "2025-06-18"):
            self.fixture.legacy_version = version
            async with connect_mcp(remote(self.fixture.url)) as dispatcher:
                self.assertFalse(
                    (await dispatcher.dispatch(call("read_value"))).is_error
                )
        self.fixture.legacy_version = None
        self.fixture.fault = "version-2024-11-05"
        self.fixture.requests.clear()
        with self.assertRaises(MCPFailure):
            async with connect_mcp(remote(self.fixture.url)):
                self.fail("unsupported protocol connected")
        self.assertNotIn("tools/call", [method for method, _ in self.fixture.requests])

    async def test_read_profile_cannot_write_and_revocation_stops_calls(self) -> None:
        cfg = remote(self.fixture.url).model_copy(
            update={
                "tools": {"read_value": "read"},
                "allow_writes": False,
            }
        )
        async with connect_mcp(cfg) as dispatcher:
            self.assertTrue(
                (await dispatcher.dispatch(call("write_value", value=5))).is_error
            )
            self.fixture.tokens = {"revoked"}
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(call("read_value"))
        self.assertEqual(self.fixture.writes, 0)

    async def test_cli_fault_diagnostics_redact_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cfg, args = Path(temporary) / "config.json", Path(temporary) / "call.json"
            cfg.write_text(remote(self.fixture.url).model_dump_json())
            args.write_text(call("read_value").model_dump_json())
            self.fixture.fault = "malformed"
            output, errors = io.StringIO(), io.StringIO()
            with (
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(errors),
                self.assertLogs("mcp", level="ERROR") as logs,
            ):
                status = await asyncio.to_thread(
                    main, ["mcp-call", "--config", str(cfg), "--call", str(args)]
                )
            text = output.getvalue() + errors.getvalue() + " ".join(logs.output)
            self.assertEqual(status, 2)
            self.assertNotIn("PRIVATE_REMOTE_FIXTURE_VALUE", text)
            self.assertNotIn("fixture-A", text)
            self.assertIn("Inspect any submitted write", text)

    async def test_bad_token_and_redirect_are_never_followed(self) -> None:
        with (
            patch.dict(os.environ, {"MCP_FIXTURE_TOKEN": "expired-token"}),
            self.assertRaises(MCPFailure),
        ):
            async with connect_mcp(remote(self.fixture.url)):
                self.fail("expired token connected")
        self.fixture.requests.clear()
        self.fixture.fault = "redirect"
        self.fixture.redirect = self.fixture.url + "/same-origin-redirect"
        with self.assertRaises(MCPFailure):
            async with connect_mcp(remote(self.fixture.url)):
                self.fail("redirect connected")
        self.assertEqual(len(self.fixture.requests), 1)
        other = MCPHTTPFixture()
        other.start()
        self.addCleanup(other.close)
        self.fixture.redirect = other.url
        with self.assertRaises(MCPFailure):
            async with connect_mcp(remote(self.fixture.url)):
                self.fail("cross-origin redirect connected")
        self.assertEqual(other.requests, [])

    async def test_wire_faults_break_session_without_resubmission(self) -> None:
        for fault in (
            "oversized_json",
            "oversized_sse",
            "compressed",
            "malformed",
            "commit_drop",
        ):
            self.fixture.fault = ""
            self.fixture.requests.clear()
            async with connect_mcp(remote(self.fixture.url)) as dispatcher:
                self.fixture.fault = fault
                with self.assertRaises(MCPFailure):
                    await dispatcher.dispatch(call("write_value", value=99))
                with self.assertRaises(MCPFailure):
                    await dispatcher.dispatch(call("read_value"))
            self.assertEqual(
                sum(method == "tools/call" for method, _ in self.fixture.requests), 1
            )
        self.assertEqual(self.fixture.writes, 1)

    async def test_timeout_and_cancellation(self) -> None:
        async with connect_mcp(remote(self.fixture.url)) as dispatcher:
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(call("slow"))
        self.fixture.cancelled.clear()
        async with connect_mcp(remote(self.fixture.url)) as dispatcher:
            task = asyncio.create_task(dispatcher.dispatch(call("slow")))
            await asyncio.sleep(0.1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(task.cancelled())
        self.assertEqual(
            sum(method == "tools/call" for method, _ in self.fixture.requests), 2
        )

    async def test_two_account_sessions_keep_tokens_separate(self) -> None:
        async with connect_mcp(remote(self.fixture.url)) as first:
            with patch.dict(os.environ, {"MCP_FIXTURE_TOKEN": "fixture-B"}):
                async with connect_mcp(remote(self.fixture.url)) as second:
                    await first.dispatch(call("read_value"))
                    await second.dispatch(call("read_value"))
        calls = [
            token for method, token in self.fixture.requests if method == "tools/call"
        ]
        self.assertEqual(calls, ["Bearer fixture-A", "Bearer fixture-B"])


class TLSRoundtripTests(IsolatedAsyncioTestCase):
    async def test_tls_trust_and_hostname_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture")])
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
                .not_valid_after(datetime.now(UTC) + timedelta(days=1))
                .add_extension(
                    x509.SubjectAlternativeName(
                        [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                    ),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            cert_path, key_path = root / "cert.pem", root / "key.pem"
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            fixture = MCPHTTPFixture(cert=cert_path, key=key_path)
            fixture.tokens = None
            fixture.start()
            try:
                kwargs = {
                    "authentication": "none",
                    "token_env": None,
                    "token_owner_uid": None,
                    "private_networks": ("127.0.0.1/32",),
                }
                with self.assertRaises(MCPFailure):
                    async with connect_mcp(remote(fixture.url, **kwargs)):
                        self.fail("untrusted certificate connected")
                async with connect_mcp(
                    remote(fixture.url, ca_file=str(cert_path), **kwargs)
                ) as dispatcher:
                    self.assertFalse(
                        (await dispatcher.dispatch(call("read_value"))).is_error
                    )
                fixture.requests.clear()
                port = httpx2.URL(fixture.url).port
                answer = [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
                ]
                with (
                    patch("anyio.getaddrinfo", new=AsyncMock(return_value=answer)),
                    self.assertRaises(MCPFailure),
                ):
                    async with connect_mcp(
                        remote(
                            f"https://wrong-name.invalid:{port}/mcp",
                            ca_file=str(cert_path),
                            **kwargs,
                        )
                    ):
                        self.fail("certificate hostname mismatch connected")
                self.assertEqual(fixture.requests, [])
            finally:
                fixture.close()
