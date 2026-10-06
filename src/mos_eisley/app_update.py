"""Bounded update discovery, trusted user policy and installation guidance."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.error import URLError

from mos_eisley.app_install import (
    atomic_json,
    install,
    installed_release,
    private_root,
)
from mos_eisley.app_release import (
    MAX_ARCHIVE,
    MAX_METADATA,
    Channel,
    Release,
    ReleaseError,
    application_version,
    download,
    parse_release,
    platform_id,
    release_metadata,
    version_key,
)

CHECK_INTERVAL = 6 * 60 * 60
FAILURE_BACKOFF = 15 * 60
SYSTEM_POLICY_PATH = Path("/etc/mos-eisley/update-policy.json")
NPM_PACKAGE = "@joshuamyers22/mos-eisley"
BREW_FORMULA = "joshuamyers22/mos-eisley/mos-eisley"


@dataclass(frozen=True)
class UpdatePolicy:
    channel: Channel = "stable"
    mode: Literal["automatic", "disabled", "managed"] = "automatic"
    skipped: str | None = None
    deferred_until: float = 0


def system_mode() -> Literal["disabled", "managed"] | None:
    try:
        info = SYSTEM_POLICY_PATH.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_mode & 0o022
        or info.st_size > 4096
    ):
        raise ReleaseError("unsafe administrator update policy")
    value: object = json.loads(SYSTEM_POLICY_PATH.read_text())
    if not isinstance(value, dict):
        raise ReleaseError("invalid administrator update policy")
    document = cast(dict[str, object], value)
    if set(document) != {"schema", "mode"} or document["schema"] != 1:
        raise ReleaseError("invalid administrator update policy")
    mode = document["mode"]
    if mode not in ("disabled", "managed"):
        raise ReleaseError("invalid administrator update mode")
    return mode


def policy(root: Path) -> UpdatePolicy:
    enforced = system_mode()
    if enforced is not None:
        return UpdatePolicy(mode=enforced)
    path = root / "update-policy.json"
    if not path.exists():
        return UpdatePolicy()
    if (
        path.is_symlink()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o077
        or path.stat().st_size > 4096
    ):
        raise ReleaseError("unsafe update policy")
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ReleaseError("invalid update policy")
    raw = cast(dict[str, object], value)
    if (
        set(raw) != {"schema", "channel", "mode", "skipped", "deferred_until"}
        or raw["schema"] != 1
    ):
        raise ReleaseError("invalid update policy")
    if raw["channel"] not in ("stable", "preview") or raw["mode"] not in (
        "automatic",
        "disabled",
        "managed",
    ):
        raise ReleaseError("invalid update policy selection")
    skipped = raw["skipped"]
    if skipped is not None:
        if not isinstance(skipped, str):
            raise ReleaseError("invalid skipped version")
        version_key(skipped)
    deferred = raw["deferred_until"]
    if (
        not isinstance(deferred, (int, float))
        or isinstance(deferred, bool)
        or not 0 <= deferred < 1e12
    ):
        raise ReleaseError("invalid update deferral")
    return UpdatePolicy(
        raw["channel"],
        raw["mode"],
        skipped,
        deferred,
    )


def save_policy(root: Path, value: UpdatePolicy) -> None:
    private_root(root)
    atomic_json(
        root / "update-policy.json",
        {
            "schema": 1,
            "channel": value.channel,
            "mode": value.mode,
            "skipped": value.skipped,
            "deferred_until": value.deferred_until,
        },
    )


def installation_origin(root: Path) -> str:
    # Frozen package-manager receipts are generated at packaging, never by a repo.
    receipt = Path(sys.executable).parent / "installation-origin.json"
    if getattr(sys, "frozen", False) and receipt.is_file():
        value = json.loads(receipt.read_text())
        if value.get("origin") in {"npm", "homebrew"}:
            return cast(str, value["origin"])
    if getattr(sys, "frozen", False) and (root / "install.json").is_file():
        value = json.loads((root / "install.json").read_text())
        return cast(str, value["origin"])
    return "developer"


def installed_version() -> str:
    return application_version()


def check(root: Path, *, force: bool = False) -> dict[str, object]:
    private_root(root)
    selection = policy(root)
    now = time.time()
    origin = installation_origin(root)
    base: dict[str, object] = {
        "installed": installed_version(),
        "channel": selection.channel,
        "origin": origin,
        "latest": None,
        "notes": None,
        "available": False,
        "cached": False,
    }
    if selection.mode != "automatic":
        return {**base, "status": selection.mode}
    cache_path = root / f"update-cache-{selection.channel}.json"
    cached: Release | None = None
    checked_at = 0.0
    last_failed = False
    try:
        if cache_path.is_symlink() or cache_path.stat().st_size > MAX_METADATA * 2:
            raise ReleaseError("unsafe update cache")
        record = json.loads(cache_path.read_text())
        checked_at = float(record["checked_at"])
        last_failed = record["failed"] is True
        if record["release"] is not None:
            cached = parse_release(record["release"].encode())
    except FileNotFoundError:
        pass
    except (ValueError, KeyError, TypeError):
        cached = None
        checked_at = 0
    interval = FAILURE_BACKOFF if last_failed else CHECK_INTERVAL
    reuse = not force and 0 <= now - checked_at < interval
    release = cached
    failed = last_failed if reuse else False
    if not reuse:
        try:
            release = parse_release(release_metadata(selection.channel))
            if release.channel != selection.channel:
                raise ReleaseError("release channel substitution")
            release.artifact(platform_id())
        except (OSError, URLError, ReleaseError) as error:
            failed = True
            # Error detail may contain untrusted URL strings, so keep it inert.
            _ = error
        atomic_json(
            cache_path,
            {
                "checked_at": now,
                "failed": failed,
                "release": None if release is None else release.raw.decode(),
            },
        )
    result = {
        **base,
        "status": "unable_to_check" if failed else "up_to_date",
        "cached": reuse or failed,
    }
    if release is not None:
        compatible = release.channel == selection.channel and any(
            a.platform == platform_id() for a in release.artifacts
        )
        newer = version_key(release.version) > version_key(installed_version())
        available = compatible and newer
        result.update(
            {
                "latest": release.version,
                "notes": release.notes,
                "source_commit": release.source_commit,
                "available": available,
                "release_url": f"https://github.com/joshuamyers22/mos-eisley/releases/tag/v{release.version}",
            }
        )
        if not failed:
            result["status"] = "available" if available else "up_to_date"
        result["notify"] = (
            available
            and not failed
            and selection.skipped != release.version
            and selection.deferred_until <= now
        )
    return result


def change_policy(root: Path, action: str, target: str | None = None) -> None:
    from dataclasses import replace

    selected = policy(root)
    if action == "later":
        selected = replace(selected, deferred_until=time.time() + 24 * 60 * 60)
    elif action == "skip" and target is not None:
        version_key(target)
        selected = replace(selected, skipped=target)
    elif action in {"automatic", "disabled", "managed"}:
        selected = replace(
            selected, mode=cast(Literal["automatic", "disabled", "managed"], action)
        )
    elif action in {"stable", "preview"}:
        selected = replace(
            selected, channel=cast(Channel, action), skipped=None, deferred_until=0
        )
    else:
        raise ReleaseError("unknown update policy action")
    save_policy(root, selected)


def update(root: Path, *, confirmed: bool, target: str | None = None) -> str:
    if not confirmed:
        raise ReleaseError("explicit confirmation required")
    selected = policy(root)
    if selected.mode != "automatic":
        raise ReleaseError(
            f"updates are {selected.mode}; change trusted user policy first"
        )
    origin = installation_origin(root)
    if origin != "standalone":
        raise ReleaseError(manual_instructions(origin, target))
    release = parse_release(release_metadata(selected.channel))
    if release.channel != selected.channel or (
        target is not None and release.version != target
    ):
        raise ReleaseError("release changed; inspect the exact target again")
    current = installed_release(root)
    if current is None:
        raise ReleaseError("no managed standalone installation")
    if version_key(release.version) <= version_key(current.version):
        raise ReleaseError("target is not newer than the current installation")
    artifact = release.artifact(platform_id())
    raw = download(artifact.url, min(MAX_ARCHIVE, artifact.size))
    metadata = json.loads((root / "install.json").read_text())
    install(root, Path(metadata["bin_dir"]), release, raw)
    return release.version


def manual_instructions(origin: str, target: str | None) -> str:
    if origin == "npm":
        return (
            "Close Mos sessions, then run: npm install --global "
            f"{NPM_PACKAGE}@{target or 'latest'}"
        )
    if origin == "homebrew":
        return f"Close Mos sessions, then run: brew upgrade {BREW_FORMULA}"
    return (
        "This is a developer/unmanaged installation. Update its selected "
        "environment using the installation documentation."
    )


def notice(result: dict[str, object]) -> str:
    if not result.get("notify"):
        return ""
    return (
        f"Mos Eisley {result['latest']} is available "
        f"(installed {result['installed']}). /update shows notes; "
        "/update later or /update skip dismisses this notice. "
        "Finish the session, then run mos update to install."
    )
