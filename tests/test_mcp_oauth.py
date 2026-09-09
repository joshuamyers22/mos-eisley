"""OAuth lifecycle and adversarial boundaries against a real HTTP fixture."""

import asyncio
import contextlib
import io
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from urllib.parse import urlencode

import httpx2
from fixtures.mcp_oauth_server import OAuthFixture

from mos_eisley.cli import main
from mos_eisley.core.protocol import ToolCallBlock
from mos_eisley.tools.mcp import MCPConfig, MCPFailure, connect_mcp
from mos_eisley.tools.mcp_http import MCPHTTPSettings
from mos_eisley.tools.mcp_oauth import OAuthCallback, OAuthController, OAuthRecord
from mos_eisley.tools.mcp_oauth_config import MCPOAuthSettings
from mos_eisley.tools.mcp_oauth_store import OAuthFailure


class MemoryKeychain:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class OAuthTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.keychain = MemoryKeychain()
        self.patches = [
            patch(
                "mos_eisley.tools.mcp_oauth_store.credential_backend",
                return_value=self.keychain,
            ),
            patch(
                "mos_eisley.tools.mcp_oauth_store.Path.home",
                return_value=Path(self.temporary.name),
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.fixture = OAuthFixture()
        self.addCleanup(self.fixture.close)
        self.settings = self.config(self.fixture)
        self.controller = OAuthController(self.settings)

    def config(self, fixture: OAuthFixture, account: str = "alice") -> MCPHTTPSettings:
        return MCPHTTPSettings(
            url=fixture.url,
            authentication="oauth",
            allow_loopback_http=True,
            oauth=MCPOAuthSettings(
                issuer=fixture.issuer,
                client_id="fixture-client",
                account=account,
                scopes=("read", "write"),
                callback_port=free_port(),
                login_timeout_seconds=5,
            ),
        )

    async def browser(self, url: str) -> None:
        async with httpx2.AsyncClient(trust_env=False) as client:
            response = await client.get(url)
            self.assertEqual(response.status_code, 302)
            callback = await client.get(response.headers["location"])
            self.assertEqual(callback.status_code, 200)

    async def expire(self, controller: OAuthController) -> None:
        raw = await controller.store.get()
        assert raw is not None
        record = OAuthRecord.model_validate_json(raw).model_copy(
            update={"expires_at": time.time() - 1}
        )
        await controller.store.set(record.model_dump_json())

    def client_config(self) -> MCPConfig:
        return MCPConfig(
            transport="streamable_http",
            http=self.settings,
            tools={"read_value": "read", "write_value": "write"},
            allow_writes=True,
        )

    async def test_login_read_write_refresh_logout(self) -> None:
        await self.controller.login(self.browser)
        async with connect_mcp(self.client_config()) as dispatcher:
            result = await dispatcher.dispatch(
                ToolCallBlock(id="write", name="write_value", args={"value": 42})
            )
            self.assertFalse(result.is_error)
            await self.expire(self.controller)
            result = await dispatcher.dispatch(
                ToolCallBlock(id="read", name="read_value", args={})
            )
            self.assertEqual(
                json.loads(result.content)["structured_content"]["value"], 42
            )
            self.assertEqual(self.fixture.refreshes, 1)
            result = await self.controller.logout()
            self.assertEqual(result["revocation"], "provider_accepted")
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(
                    ToolCallBlock(id="after-logout", name="read_value", args={})
                )
        self.assertEqual(self.fixture.http.writes, 1)
        self.assertEqual(self.fixture.revocations, 2)
        self.assertIsNone(await self.controller.store.get())
        with self.assertRaises(OAuthFailure):
            await self.controller.access_token()

    async def test_concurrent_refresh_only_exchanges_once(self) -> None:
        await self.controller.login(self.browser)
        await self.expire(self.controller)
        other = OAuthController(self.settings)
        tokens = await asyncio.gather(
            self.controller.access_token(), other.access_token()
        )
        self.assertEqual(tokens[0], tokens[1])
        self.assertEqual(self.fixture.refreshes, 1)

    async def test_accounts_servers_clients_and_owner_are_isolated(self) -> None:
        second = OAuthFixture()
        self.addCleanup(second.close)
        bob = OAuthController(self.config(self.fixture, "bob"))
        other = OAuthController(self.config(second))
        await self.controller.login(self.browser)
        await bob.login(self.browser)
        await other.login(self.browser)
        self.assertEqual(len(self.keychain.values), 3)
        await self.expire(bob)
        await bob.access_token()
        self.assertEqual(self.fixture.refreshes, 1)
        self.assertEqual(second.refreshes, 0)
        await self.controller.logout()
        self.assertTrue((await bob.access_token()).get_secret_value())
        self.assertTrue((await other.access_token()).get_secret_value())
        with (
            patch("os.geteuid", return_value=os.geteuid() + 1),
            self.assertRaises(OAuthFailure),
        ):
            await bob.access_token()

    async def test_revocation_fails_session_without_refresh_or_retry(self) -> None:
        await self.controller.login(self.browser)
        async with connect_mcp(self.client_config()) as dispatcher:
            assert self.fixture.http.tokens is not None
            self.fixture.http.tokens.clear()
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(
                    ToolCallBlock(id="write", name="write_value", args={"value": 1})
                )
        self.assertEqual(self.fixture.refreshes, 0)
        self.assertEqual(self.fixture.http.writes, 0)
        self.assertIsNone(await self.controller.store.get())
        with self.assertRaises(MCPFailure):
            async with connect_mcp(self.client_config()):
                self.fail("revoked credentials reconnected")

    async def test_lost_write_response_does_not_repeat(self) -> None:
        await self.controller.login(self.browser)
        async with connect_mcp(self.client_config()) as dispatcher:
            self.fixture.http.fault = "commit_drop"
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(
                    ToolCallBlock(id="write", name="write_value", args={"value": 2})
                )
        self.assertEqual(self.fixture.http.writes, 1)
        self.assertEqual(self.fixture.refreshes, 0)

    async def test_invalid_discovery_never_sends_code_or_token(self) -> None:
        for fault in (
            "issuer",
            "resource",
            "evil_hint",
            "evil_token",
            "redirect_metadata",
            "pkce",
        ):
            self.fixture.fault = fault
            with (
                self.subTest(fault=fault),
                self.assertRaises((OAuthFailure, ValueError)),
            ):
                await self.controller.login(self.browser)
            self.assertEqual(self.fixture.exchanges, 0)
            self.assertIsNone(await self.controller.store.get())

    async def test_oidc_fallback_and_explicit_reauthentication(self) -> None:
        self.fixture.fault = "oidc"
        await self.controller.login(self.browser)
        self.assertIn("/.well-known/openid-configuration", self.fixture.auth_requests)
        self.fixture.fault = "denied"
        with self.assertRaises(OAuthFailure):
            await self.controller.login(self.browser)
        self.assertIsNone(await self.controller.store.get())
        self.fixture.fault = ""
        await self.controller.login(self.browser)
        self.assertEqual(self.fixture.exchanges, 2)

    async def test_scope_and_resource_mismatch_in_tokens_rejected(self) -> None:
        for fault in ("scope", "token_resource"):
            self.fixture.fault = fault
            with self.assertRaises(OAuthFailure):
                await self.controller.login(self.browser)
            self.assertIsNone(await self.controller.store.get())

    async def test_refresh_failure_cannot_resubmit_rotated_token(self) -> None:
        for fault in ("refresh_denied", "refresh_drop"):
            self.fixture.fault = ""
            await self.controller.login(self.browser)
            await self.expire(self.controller)
            self.fixture.fault = fault
            before = self.fixture.refreshes
            with self.assertRaises(OAuthFailure):
                await self.controller.access_token()
            with self.assertRaises(OAuthFailure):
                await self.controller.access_token()
            self.assertEqual(self.fixture.refreshes, before + 1)

    async def test_logout_reports_failed_revocation_but_clears_local_record(
        self,
    ) -> None:
        await self.controller.login(self.browser)
        self.fixture.fault = "revocation"
        result = await self.controller.logout()
        self.assertEqual(result["revocation"], "failed_or_incomplete")
        self.assertIsNone(await self.controller.store.get())
        self.assertEqual(
            (await self.controller.logout())["revocation"], "no_credentials"
        )

    async def test_callback_state_issuer_duplicates_and_replay(self) -> None:
        port = free_port()
        async with (
            OAuthCallback(
                port, "expected-state", self.fixture.issuer, True
            ) as callback,
            httpx2.AsyncClient(trust_env=False) as client,
        ):
            base = f"http://127.0.0.1:{port}/oauth/callback?"
            good = {
                "state": "expected-state",
                "iss": self.fixture.issuer,
                "code": "one-use",
            }
            for query in (
                urlencode({**good, "state": "wrong"}),
                urlencode({**good, "iss": "https://wrong.invalid"}),
                urlencode({"state": "expected-state", "code": "one-use"}),
                urlencode(good) + "&code=duplicate",
            ):
                self.assertEqual((await client.get(base + query)).status_code, 400)
                self.assertFalse(callback.code.done())
            self.assertEqual(
                (await client.get(base + urlencode(good))).status_code, 200
            )
            self.assertEqual(await callback.code, "one-use")
            self.assertEqual(
                (await client.get(base + urlencode(good))).status_code, 400
            )

    async def test_callback_timeout_releases_port(self) -> None:
        async def no_browser(_: str) -> None:
            pass

        with self.assertRaises(TimeoutError):
            await self.controller.login(no_browser)
        assert self.settings.oauth is not None
        async with OAuthCallback(
            self.settings.oauth.callback_port, "new", self.fixture.issuer, True
        ):
            pass
        self.assertIsNone(await self.controller.store.get())

    async def test_private_lock_directory_and_symlink_denied(self) -> None:
        directory = self.controller.store.directory
        directory.mkdir(mode=0o755)
        with self.assertRaises(OAuthFailure):
            await self.controller.access_token()
        directory.chmod(0o700)
        (directory / (self.controller.binding + ".lock")).symlink_to(
            Path(self.temporary.name) / "outside"
        )
        with self.assertRaises(OSError):
            await self.controller.access_token()

    async def test_cli_login_logout_and_no_token_output(self) -> None:
        config = Path(self.temporary.name) / "oauth.json"
        config.write_text(self.client_config().model_dump_json())
        output, errors = io.StringIO(), io.StringIO()

        def browser(url: str, *args: Any, **kwargs: Any) -> bool:
            asyncio.run(self.browser(url))
            return True

        with (
            patch("webbrowser.open", side_effect=browser),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            result = await asyncio.to_thread(
                main, ["mcp-login", "--config", str(config), "--open-browser"]
            )
            self.assertEqual(result, 0)
        raw = await self.controller.store.get()
        assert raw is not None
        record = OAuthRecord.model_validate_json(raw)
        self.assertNotIn(record.access_token, output.getvalue() + errors.getvalue())
        self.assertNotIn(record.refresh_token, output.getvalue() + errors.getvalue())
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                await asyncio.to_thread(main, ["mcp-logout", "--config", str(config)]),
                0,
            )

    async def test_keychain_unavailable_has_no_fallback_or_secret_error(self) -> None:
        with (
            patch.object(
                self.keychain, "get_password", side_effect=RuntimeError("SECRET")
            ),
            self.assertRaises(OAuthFailure) as error,
        ):
            await self.controller.access_token()
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(self.keychain.values, {})

    async def test_corrupt_keychain_record_is_redacted(self) -> None:
        await self.controller.store.set('{"access_token":"PRIVATE-BROKEN-TOKEN"}')
        with self.assertRaises(OAuthFailure) as error:
            await self.controller.access_token()
        self.assertNotIn("PRIVATE-BROKEN-TOKEN", str(error.exception))

    async def test_cancelled_save_keeps_lock_until_logout_can_remove_it(self) -> None:
        entered, release = threading.Event(), threading.Event()
        original = self.keychain.set_password

        def delayed(service: str, key: str, value: str) -> None:
            entered.set()
            release.wait(5)
            original(service, key, value)

        async def save() -> None:
            async with self.controller.store.locked():
                await self.controller.store.set("synthetic")

        with patch.object(self.keychain, "set_password", side_effect=delayed):
            task = asyncio.create_task(save())
            await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            logout = asyncio.create_task(self.controller.invalidate())
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.sleep(0.05)
            self.assertFalse(logout.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await logout
        self.assertIsNone(await self.controller.store.get())

    async def test_scope_change_and_uid_change_do_not_reuse_credentials(self) -> None:
        await self.controller.login(self.browser)
        assert self.settings.oauth is not None
        for changes in ({"scopes": ("read",)}, {"client_id": "another-client"}):
            oauth = self.settings.oauth.model_copy(update=changes)
            other = OAuthController(self.settings.model_copy(update={"oauth": oauth}))
            with self.assertRaises(OAuthFailure):
                await other.access_token()
        with patch("os.geteuid", return_value=os.geteuid() + 1):
            other = OAuthController(self.settings)
            self.assertNotEqual(other.binding, self.controller.binding)
            self.assertIsNone(await other.store.get())

    async def test_insufficient_configured_scopes_fail_before_authorization(
        self,
    ) -> None:
        assert self.settings.oauth is not None
        oauth = self.settings.oauth.model_copy(update={"scopes": ("write",)})
        controller = OAuthController(self.settings.model_copy(update={"oauth": oauth}))
        with self.assertRaises(OAuthFailure):
            await controller.login(self.browser)
        self.assertNotIn("/authorize", self.fixture.auth_requests)

    async def test_cancelled_login_closes_callback_and_leaves_no_credentials(
        self,
    ) -> None:
        ready = asyncio.Event()

        async def no_browser(_: str) -> None:
            ready.set()

        task = asyncio.create_task(self.controller.login(no_browser))
        await ready.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        assert self.settings.oauth is not None
        async with OAuthCallback(
            self.settings.oauth.callback_port, "new", self.fixture.issuer, True
        ):
            pass
        self.assertIsNone(await self.controller.store.get())
