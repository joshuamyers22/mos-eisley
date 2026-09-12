"""Install the wheel and exercise replay plus stdio and HTTP MCP calls."""

import importlib.util
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    wheel = Path("dist/mos_eisley-0.1.0-py3-none-any.whl").resolve()
    with TemporaryDirectory(prefix="mos-eisley-wheel-") as directory:
        root = Path(directory)
        python = root / "venv/bin/python"
        subprocess.run(
            ["uv", "venv", str(root / "venv"), "--python", "3.12"], check=True
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "-r",
                "requirements.runtime.txt",
            ],
            check=True,
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            check=True,
        )
        command = str(root / "venv/bin/mos-eisley")
        demo = subprocess.run(
            [command, "demo", "--output", str(root / "runs"), "--json"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if demo.returncode != 1:
            raise ValueError("wheel demo did not return expected revise status")
        event = json.loads(demo.stdout.splitlines()[0])
        subprocess.run([command, "replay", event["path"]], cwd=root, check=True)
        agent = subprocess.run(
            [
                command,
                "agent-demo",
                "--output",
                str(root / "agent-runs"),
                "--json",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        agent_event = json.loads(agent.stdout)
        subprocess.run(
            [command, "agent-replay", agent_event["path"]], cwd=root, check=True
        )
        analysis = subprocess.run(
            [command, "analysis-demo"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        if json.loads(analysis.stdout)["answer"]["result_ids"] != ["result-0002"]:
            raise ValueError("installed analytical fixture returned wrong evidence")
        server = root / "mcp_fixture.py"
        server.write_text(Path("tests/fixtures/mcp_server.py").read_text())
        config = root / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "command": str(python),
                    "args": [str(server)],
                    "cwd": str(root),
                    "tools": {"echo": "read"},
                }
            )
        )
        call = root / "call.json"
        call.write_text(
            json.dumps(
                {
                    "id": "wheel-call",
                    "name": "echo",
                    "args": {"value": "wheel-fixture"},
                }
            )
        )
        mcp = subprocess.run(
            [command, "mcp-call", "--config", str(config), "--call", str(call)],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(mcp.stdout)
        if result["is_error"] or json.loads(result["content"])[
            "structured_content"
        ] != {"value": "wheel-fixture"}:
            raise ValueError("installed MCP client returned the wrong fixture")
        spec = importlib.util.spec_from_file_location(
            "http_fixture", "tests/fixtures/mcp_http_server.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture = module.MCPHTTPFixture()
        fixture.tokens = None
        fixture.start()
        try:
            config.write_text(
                json.dumps(
                    {
                        "transport": "streamable_http",
                        "http": {
                            "url": fixture.url,
                            "authentication": "none",
                            "allow_loopback_http": True,
                        },
                        "tools": {"read_value": "read", "write_value": "write"},
                        "allow_writes": True,
                    }
                )
            )
            for name, args, expected in (
                ("write_value", {"value": 42}, {"value": 42}),
                ("read_value", {}, {"value": 42, "writes": 1}),
            ):
                call.write_text(json.dumps({"id": name, "name": name, "args": args}))
                remote = subprocess.run(
                    [command, "mcp-call", "--config", str(config), "--call", str(call)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                result = json.loads(remote.stdout)
                if (
                    result["is_error"]
                    or json.loads(result["content"])["structured_content"] != expected
                ):
                    raise ValueError("installed HTTP MCP client returned wrong data")
        finally:
            fixture.close()
        # Run the OAuth contract from the installed wheel. The fixture uses only
        # synthetic credentials and an in-memory keychain, never the host vault.
        fixtures = root / "fixtures"
        fixtures.mkdir()
        (fixtures / "__init__.py").write_text("")
        for name in (
            "mcp_http_server.py",
            "mcp_oauth_server.py",
            "mcp_server.py",
            "mcp_schema_server.py",
            "mcp_schema_tools.py",
        ):
            (fixtures / name).write_text((Path("tests/fixtures") / name).read_text())
        for name in (
            "test_conversation.py",
            "test_conversation_navigation.py",
            "test_conversation_review.py",
            "test_conversation_composer.py",
            "test_conversation_steering.py",
            "test_conversation_tui.py",
            "test_conversation_startup.py",
            "test_conversation_launch_prompt.py",
            "test_conversation_names.py",
            "test_conversation_picker.py",
            "test_conversation_directory.py",
            "test_conversation_switch.py",
            "test_conversation_project.py",
            "test_conversation_memory_project.py",
            "test_conversation_memory_mapping.py",
            "test_conversation_memory_registry.py",
            "test_conversation_memory_registry_history.py",
            "test_conversation_memory_registry_import.py",
            "test_conversation_memory_registry_retention.py",
            "test_conversation_memory_retention.py",
            "test_conversation_memory_migration.py",
            "test_conversation_memory_recovery.py",
            "test_conversation_memory_resolution.py",
            "test_conversation_memory_relocation.py",
            "test_conversation_memory_mapped_resolution.py",
            "test_conversation_memory_cleanup.py",
            "test_conversation_memory_batch_cleanup.py",
            "test_conversation_memory_staging.py",
            "test_conversation_memory_staging_review.py",
            "test_conversation_memory_backup_discard.py",
            "test_conversation_memory.py",
            "test_conversation_memory_refresh.py",
            "test_conversation_memory_commands.py",
            "test_conversation_remember.py",
            "test_conversation_storage_budgets.py",
            "test_conversation_sqlite.py",
            "test_conversation_migration.py",
            "test_conversation_batch_migration.py",
            "test_conversation_transfer.py",
            "test_conversation_batch_transfer.py",
            "test_conversation_export.py",
            "test_conversation_same_root_export.py",
            "test_conversation_batch_export.py",
            "test_conversation_cleanup.py",
            "test_conversation_retention.py",
            "test_conversation_prune.py",
            "test_conversation_batch_prune.py",
            "test_conversation_transcript.py",
            "test_conversation_history.py",
            "test_conversation_artifacts.py",
            "test_conversation_resume.py",
            "test_conversation_checkpoint_saves.py",
            "test_conversation_context.py",
            "test_conversation_context_preview.py",
            "test_conversation_request_admission.py",
            "test_conversation_admission_inspection.py",
            "test_conversation_working_state.py",
            "test_conversation_cold_resume.py",
            "test_conversation_input_limits.py",
            "test_conversation_pending.py",
            "test_conversation_streamed_inputs.py",
            "test_conversation_native_validation.py",
            "test_conversation_read_cache.py",
            "test_mcp_oauth.py",
            "test_mcp_schema.py",
            "test_analysis.py",
            "test_analysis_spending.py",
            "test_analysis_evidence.py",
            "test_analysis_evaluation.py",
            "test_analysis_raw.py",
            "test_analysis_schedule.py",
        ):
            (root / name).write_text((Path("tests") / name).read_text())
        subprocess.run(
            [
                str(python),
                "-m",
                "unittest",
                "discover",
                "-s",
                str(root),
                "-p",
                "test_*.py",
            ],
            cwd=root,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
