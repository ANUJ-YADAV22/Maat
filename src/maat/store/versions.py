"""Config version store: bootstrap, adopt, rollback (as a new version), diff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maat.config_model import Charter, ConfigError, apply_patch, config_hash, diff, normalize
from maat.db import transaction
from maat.repo import Repo


def ensure_initial(repo: Repo, config_path: Path) -> int:
    """Insert config_v1.json as version 1 if no version exists; return the active version."""
    latest = repo.latest_version()
    if latest is not None:
        return latest
    cfg = normalize(json.loads(config_path.read_text()))
    cfg["version"] = 1
    repo.insert_config_version(1, None, cfg, config_hash(cfg))
    repo.audit("config.bootstrap", "system", {"version": 1, "hash": config_hash(cfg)})
    return 1


def active_version(repo: Repo) -> int:
    version = repo.latest_version()
    if version is None:
        raise RuntimeError("no config version; call ensure_initial first")
    return version


def active_config(repo: Repo) -> dict[str, Any]:
    row = repo.get_config_version(active_version(repo))
    assert row is not None
    return row["config_json"]


ADOPTABLE = ("proposed", "gating", "quarantined", "inconclusive")


class VersionError(Exception):
    """A version operation was refused (carries a machine code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def adopt(
    repo: Repo, patch_id: str, actor: str, charter: Charter | None = None, reason: str = ""
) -> int:
    """Apply a patch to the active config and write the new version in one transaction.

    Also appends the patch's witness test to the accumulated suite. Phase 3 calls this only after
    the gate decides ``adopt`` (or a human approves a quarantined patch).
    """
    patch = repo.get_patch(patch_id)
    if patch is None:
        raise VersionError("unknown_patch", f"patch {patch_id} does not exist")
    if patch["status"] not in ADOPTABLE:
        raise VersionError("bad_status", f"patch is {patch['status']}, cannot adopt")
    parent = active_version(repo)
    base = active_config(repo)
    try:
        new = apply_patch(base, patch["ops_json"], charter)
    except ConfigError as exc:
        repo.audit("patch.adopt_blocked", actor, {"patch_id": patch_id, "error": str(exc)})
        raise VersionError("apply_failed", str(exc)) from exc
    if config_hash(new) == config_hash(base):
        raise VersionError("no_change", "patch does not change the config")
    version = parent + 1
    new["version"] = version
    witness = patch["witness_json"]
    with transaction(repo.conn):
        repo.insert_config_version(version, parent, new, config_hash(new), patch_id)
        repo.upsert_test(
            f"acc_{patch_id}",
            "accumulated",
            witness["family"],
            witness["input"],
            witness["checker"],
            ["accumulated", patch_id],
        )
        repo.set_patch_status(patch_id, "adopted")
        repo.audit(
            "patch.adopted",
            actor,
            {"patch_id": patch_id, "version": version, "parent": parent, "reason": reason},
        )
    return version


def rollback(repo: Repo, to_version: int, reason: str, actor: str) -> int:
    """Restore ``to_version`` by creating a new version that copies it; history is never edited.

    Patches adopted after ``to_version`` become rolled_back and their witness tests leave the
    accumulated suite (the fixes they covered are no longer in the config).
    """
    target = repo.get_config_version(to_version)
    if target is None:
        raise VersionError("unknown_version", f"version {to_version} does not exist")
    current = active_version(repo)
    if to_version == current:
        raise VersionError("noop", "already on that version")
    undone = [
        v["created_from_patch"]
        for v in repo.list_config_versions()
        if v["version"] > to_version and v["created_from_patch"]
    ]
    new = dict(target["config_json"])
    version = current + 1
    new["version"] = version
    with transaction(repo.conn):
        repo.insert_config_version(version, current, new, target["config_hash"], None, "rollback")
        for pid in undone:
            if (p := repo.get_patch(pid)) and p["status"] == "adopted":
                repo.set_patch_status(pid, "rolled_back")
            repo.delete_test(f"acc_{pid}")
        repo.audit(
            "config.rollback",
            actor,
            {
                "from_version": current,
                "to_version": to_version,
                "new_version": version,
                "reason": reason,
                "patches_rolled_back": undone,
            },
        )
    return version


def diff_versions(repo: Repo, a: int, b: int) -> list[dict[str, Any]]:
    ca, cb = repo.get_config_version(a), repo.get_config_version(b)
    if ca is None or cb is None:
        raise VersionError("unknown_version", "version does not exist")
    return diff(ca["config_json"], cb["config_json"])
