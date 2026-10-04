"""Frozen synthetic legacy bytes/digests; never read user stores or credentials."""

import hashlib
import json
import sys
import unittest
from unittest.mock import patch

MEMORY = (
    b'{"enabled":true,"owner_uid":1000,"revision":7,"schema_version":1,'
    b'"scope":"user","source":"explicit_user","text":"caf\xc3\xa9\\nkeep exact",'
    b'"updated_at":"2026-01-02T03:04:05Z","workspace":null}'
)
MEMORY_SHA = "0de6f04db659b0291e13e9ab00cafabbe274da882c74c4b57a6a71d81069a1dc"
SNAPSHOT = b'{"document":' + MEMORY + b',"sha256":"' + MEMORY_SHA.encode() + b'"}'
SNAPSHOT_SHA = "1466029b1ed9f588f2e464e2b80cdc7553a541d385d0e76d57f7860e0acfcc71"
REGISTRY = (
    b'{"mappings":[{"target":{"device":18446744073709551615,'
    b'"inode":18446744073709551614,"path":"/synthetic/memory"},'
    b'"workspace":{"device":1,"inode":2,"path":"/synthetic/workspace"}}],'
    b'"owner_uid":1000,"revision":9,"schema_version":1}'
)
REGISTRY_SHA = "8364228cb0892a954767c1c61785dee8b89805c7ad33787ad9f50a7294dcc603"
EVIDENCE = (
    b'{"explanation":"synthetic fixture","kind":"citation",'
    b'"quote":"retain bytes","source":"spec"}'
)
EVIDENCE_SHA = "df5cc03854c0cc47cfe91acf45057f979c0d3aad82e989a8a2c12023e88ebb93"
OAUTH_BINDING = (
    b'{"account": "fixture-account", "client": "fixture-client", '
    b'"issuer": "https://issuer.invalid", "resource": "https://example.invalid/mcp", '
    b'"scopes": ["read", "write"], "uid": 1000}'
)
OAUTH_SHA = "ad379fa2d3634b02b5826467d3db6af6d07ace01e056a5333e4d37714975bcbf"
MCP_HTTP = (
    b'{"allow_loopback_http":false,"authentication":"bearer","ca_file":null,'
    b'"max_response_bytes":262144,"oauth":null,"private_networks":[],"token_env":'
    b'"FIXTURE_TOKEN","token_owner_uid":1000,"url":"https://example.invalid/mcp"}'
)
MCP_HTTP_SHA = "dc143372bc73a805f85d447f375927aaadddb931a32e338eab8df3c49aa081b6"


class LegacyFixtureBytesTests(unittest.TestCase):
    def test_frozen_literal_bytes_and_hashes(self) -> None:
        for payload, expected in (
            (MEMORY, MEMORY_SHA),
            (SNAPSHOT, SNAPSHOT_SHA),
            (REGISTRY, REGISTRY_SHA),
            (EVIDENCE, EVIDENCE_SHA),
            (OAUTH_BINDING, OAUTH_SHA),
            (MCP_HTTP, MCP_HTTP_SHA),
        ):
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)

    def test_new_codec_does_not_reinterpret_legacy_records(self) -> None:
        from mos_eisley.platform.identity_wire import (
            IdentityWireError,
            decode_file_identity,
            decode_owner_binding,
            decode_principal,
        )

        for payload in (MEMORY, SNAPSHOT, REGISTRY, EVIDENCE, OAUTH_BINDING, MCP_HTTP):
            for decoder in (
                decode_principal,
                decode_owner_binding,
                decode_file_identity,
            ):
                with self.assertRaises(IdentityWireError):
                    decoder(payload)


@unittest.skipUnless(
    sys.platform in {"darwin", "linux"}, "legacy readers are POSIX-only"
)
class LegacyReaderFixturesTests(unittest.TestCase):
    def test_memory_null_defaults_unicode_and_snapshot_digest(self) -> None:
        from mos_eisley.conversation_memory import MemoryDocument, MemorySnapshot
        from mos_eisley.core.models import canonical_bytes

        document = MemoryDocument.model_validate_json(MEMORY)
        self.assertEqual(document.text, "café\nkeep exact")
        self.assertEqual(document.owner_uid, 1000)
        self.assertEqual(canonical_bytes(document), MEMORY)
        snapshot = MemorySnapshot.model_validate_json(SNAPSHOT)
        self.assertEqual(canonical_bytes(snapshot), SNAPSHOT)
        with self.assertRaises(ValueError):
            MemorySnapshot.model_validate_json(SNAPSHOT.replace(b"caf", b"CAF"))

    def test_registry_identity_width_owner_and_backup_name(self) -> None:
        from mos_eisley.conversation_memory_registry import (
            decode_registry,
            mapping_backup_name,
        )
        from mos_eisley.core.models import canonical_bytes

        with patch("os.getuid", return_value=1000):
            registry = decode_registry(REGISTRY)
            self.assertEqual(canonical_bytes(registry), REGISTRY)
            self.assertEqual(registry.mappings[0].target.device, 2**64 - 1)
            self.assertEqual(registry.mappings[0].target.inode, 2**64 - 2)
        self.assertEqual(
            mapping_backup_name(REGISTRY), "mapping-backup-" + REGISTRY_SHA + ".json"
        )
        with patch("os.getuid", return_value=1001), self.assertRaises(ValueError):
            decode_registry(REGISTRY)
        with patch("os.getuid", return_value=1000), self.assertRaises(ValueError):
            decode_registry(b" " + REGISTRY)

    def test_optional_fields_still_omit_and_original_strings_stay_exact(self) -> None:
        from mos_eisley.core.models import Evidence, canonical_bytes

        value = Evidence.model_validate_json(EVIDENCE)
        self.assertEqual(canonical_bytes(value), EVIDENCE)
        self.assertNotIn(b"source_unit", canonical_bytes(value))
        source = (
            b'{ "source":"spec", "quote":"retain bytes", "kind":"citation", '
            b'"explanation":"synthetic fixture" }'
        )
        self.assertNotEqual(hashlib.sha256(source).hexdigest(), EVIDENCE_SHA)
        self.assertEqual(
            canonical_bytes(Evidence.model_validate_json(source)), EVIDENCE
        )

    def test_legacy_reader_refuses_new_version_and_owner_field(self) -> None:
        from mos_eisley.conversation_memory import MemoryDocument
        from mos_eisley.conversation_memory_registry import MemoryMappingRegistry

        for model, payload in (
            (MemoryDocument, MEMORY),
            (MemoryMappingRegistry, REGISTRY),
        ):
            obj = json.loads(payload)
            obj["schema_version"] = 2
            with self.assertRaises(ValueError):
                model.model_validate_json(json.dumps(obj))
            obj["schema_version"] = 1
            obj["owner"] = {
                "namespace_id": "0" * 32,
                "principal": {"kind": "posix-uid", "uid": obj.pop("owner_uid")},
            }
            with self.assertRaises(ValueError):
                model.model_validate_json(json.dumps(obj))

    def test_oauth_controller_keeps_legacy_binding_encoder(self) -> None:
        from mos_eisley.core.models import canonical_bytes
        from mos_eisley.tools.mcp_http import MCPHTTPSettings
        from mos_eisley.tools.mcp_oauth import OAuthController
        from mos_eisley.tools.mcp_oauth_config import MCPOAuthSettings
        from mos_eisley.tools.mcp_oauth_store import OAuthStore

        http = MCPHTTPSettings.model_validate_json(MCP_HTTP)
        self.assertEqual(http.token_owner_uid, 1000)
        self.assertEqual(canonical_bytes(http), MCP_HTTP)
        self.assertEqual(OAuthStore.service, "mos-eisley.mcp.oauth.v1")

        settings = MCPHTTPSettings(
            url="https://example.invalid/mcp",
            authentication="oauth",
            oauth=MCPOAuthSettings(
                issuer="https://issuer.invalid",
                client_id="fixture-client",
                account="fixture-account",
                scopes=("read", "write"),
                callback_port=49152,
            ),
        )
        # Constructor is inspected only with the entire store replaced: no vault access.
        with (
            patch("os.geteuid", return_value=1000),
            patch("mos_eisley.tools.mcp_oauth.OAuthStore") as store,
        ):
            controller = OAuthController(settings)
            self.assertEqual(controller.binding, OAUTH_SHA)
            store.assert_called_once_with(OAUTH_SHA)
        self.assertNotEqual(
            hashlib.sha256(
                json.dumps(
                    json.loads(OAUTH_BINDING), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            OAUTH_SHA,
        )


if __name__ == "__main__":
    unittest.main()
