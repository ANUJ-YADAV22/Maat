"""Config schema, pure patch application, stable hashing and diffing.

The config is the only thing that ever changes in the agent (memory, rules, tool policy,
workflow). ``apply_patch`` is a pure function. The content hash ignores ``version`` so identical
content shares replay-cache entries across sandbox and adopted copies.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ConfigError(ValueError):
    """An op or config is structurally invalid."""


class ProtectedViolation(ConfigError):
    """An op would remove or weaken a protected item (defense in depth with Lock 4)."""


class MemoryItem(BaseModel):
    id: str
    subject: str
    attribute: str
    value: float | str
    text: str = ""
    source_patch: str | None = None
    protected: bool = False


class Rule(BaseModel):
    id: str
    text: str
    applies_to: list[str] = Field(default_factory=list)
    protected: bool = False


class ToolPolicy(BaseModel):
    """``require``: tools that must be called. ``ground``: tools whose output must be used."""

    require: list[str] = Field(default_factory=list)
    ground: list[str] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)


class Config(BaseModel):
    version: int = 1
    memory: list[MemoryItem] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    tool_policy: dict[str, ToolPolicy] = Field(default_factory=dict)
    workflow: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_ids(self) -> Config:
        for name, items in (("memory", self.memory), ("rules", self.rules)):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate ids in {name}")
        return self


class Op(BaseModel):
    """One edit. Paths: memory/<id>, rules/<id>, tool_policy/<fam>, workflow/<fam>[/<step>]."""

    op: Literal["add", "replace", "remove", "reorder"]
    path: str
    value: Any = None


class Charter(BaseModel):
    checklist_items: list[str] = Field(default_factory=list)
    required_workflow_steps: dict[str, list[str]] = Field(default_factory=dict)
    required_tools: dict[str, list[str]] = Field(default_factory=dict)
    required_fields: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_rule_patterns: list[str] = Field(default_factory=list)


def load_charter(path: Path) -> Charter:
    return Charter(**yaml.safe_load(path.read_text()))


def normalize(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the canonical dict form of a config."""
    return Config.model_validate(config).model_dump(mode="json")


def config_hash(config: dict[str, Any]) -> str:
    """Stable 16-hex content hash; ``version`` is excluded on purpose."""
    body = {k: v for k, v in normalize(config).items() if k != "version"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _find(items: list[dict[str, Any]], item_id: str) -> int:
    for i, it in enumerate(items):
        if it["id"] == item_id:
            return i
    return -1


def _apply_one(cfg: dict[str, Any], op: Op) -> None:
    parts = op.path.split("/")
    section = parts[0]
    if section in ("memory", "rules"):
        if len(parts) != 2:
            raise ConfigError(f"bad path {op.path}")
        items, item_id = cfg[section], parts[1]
        idx = _find(items, item_id)
        if op.op == "add":
            if idx >= 0:
                raise ConfigError(f"{op.path} already exists")
            if not isinstance(op.value, dict) or op.value.get("id") != item_id:
                raise ConfigError(f"add {op.path}: value must be an object with id={item_id}")
            items.append(copy.deepcopy(op.value))
        elif op.op == "replace":
            if idx < 0:
                raise ConfigError(f"{op.path} does not exist")
            if not isinstance(op.value, dict) or op.value.get("id") != item_id:
                raise ConfigError(f"replace {op.path}: value must be an object with id={item_id}")
            items[idx] = copy.deepcopy(op.value)
        elif op.op == "remove":
            if idx < 0:
                raise ConfigError(f"{op.path} does not exist")
            del items[idx]
        else:
            raise ConfigError(f"{op.op} not valid for {section}")
    elif section == "tool_policy":
        if len(parts) != 2:
            raise ConfigError(f"bad path {op.path}")
        fam = parts[1]
        if op.op in ("add", "replace"):
            if op.op == "add" and fam in cfg["tool_policy"]:
                raise ConfigError(f"{op.path} already exists")
            if op.op == "replace" and fam not in cfg["tool_policy"]:
                raise ConfigError(f"{op.path} does not exist")
            cfg["tool_policy"][fam] = copy.deepcopy(op.value)
        elif op.op == "remove":
            if fam not in cfg["tool_policy"]:
                raise ConfigError(f"{op.path} does not exist")
            del cfg["tool_policy"][fam]
        else:
            raise ConfigError(f"{op.op} not valid for tool_policy")
    elif section == "workflow":
        fam = parts[1] if len(parts) > 1 else ""
        steps = cfg["workflow"].setdefault(fam, [])
        if len(parts) == 3 and op.op == "remove":
            if parts[2] not in steps:
                raise ConfigError(f"{op.path} does not exist")
            steps.remove(parts[2])
        elif len(parts) == 2 and op.op == "add":
            val = op.value
            step, index = (val["step"], val.get("index")) if isinstance(val, dict) else (val, None)
            if step in steps:
                raise ConfigError(f"step {step} already in workflow/{fam}")
            steps.insert(len(steps) if index is None else int(index), step)
        elif len(parts) == 2 and op.op in ("replace", "reorder"):
            if not isinstance(op.value, list):
                raise ConfigError(f"{op.op} {op.path}: value must be a list of steps")
            if op.op == "reorder" and sorted(op.value) != sorted(steps):
                raise ConfigError(f"reorder {op.path}: must be a permutation of existing steps")
            cfg["workflow"][fam] = list(op.value)
        else:
            raise ConfigError(f"unsupported op {op.op} on {op.path}")
    else:
        raise ConfigError(f"unknown config section in path {op.path}")


def protected_violations(
    old: dict[str, Any], new: dict[str, Any], charter: Charter | None = None
) -> list[str]:
    """List ways ``new`` removes or weakens protected items of ``old`` (empty means safe)."""
    bad: list[str] = []
    for section in ("memory", "rules"):
        new_by_id = {i["id"]: i for i in new[section]}
        for item in old[section]:
            if item.get("protected") and new_by_id.get(item["id"]) != item:
                bad.append(f"protected {section}/{item['id']} removed or modified")
    if charter is None:
        return bad
    for fam, steps in charter.required_workflow_steps.items():
        have = new["workflow"].get(fam, [])
        bad += [f"workflow/{fam} lost required step {s}" for s in steps if s not in have]
    for fam, tools in charter.required_tools.items():
        have = new["tool_policy"].get(fam, {}).get("require", [])
        bad += [f"tool_policy/{fam} lost required tool {t}" for t in tools if t not in have]
    old_rules = {r["id"]: r for r in old["rules"]}
    for rule in new["rules"]:
        if old_rules.get(rule["id"]) == rule:
            continue
        for pat in charter.forbidden_rule_patterns:
            if re.search(pat, rule["text"], re.I):
                bad.append(f"rules/{rule['id']} instructs skipping or weakening a safety check")
                break
    return bad


def apply_patch(
    config: dict[str, Any],
    ops: list[Op | dict[str, Any]],
    charter: Charter | None = None,
    enforce: bool = True,
) -> dict[str, Any]:
    """Return a new config with ``ops`` applied. Pure: the input is never mutated.

    Raises ConfigError for malformed ops and ProtectedViolation when a protected item would be
    removed or weakened (and, if a charter is supplied, when charter rules would be broken).
    ``enforce=False`` skips those checks; it exists only so the gate can build a throw-away sandbox
    config to measure a violating patch (Lock 4 then vetoes it). Never persist such a config.
    """
    new = copy.deepcopy(normalize(config))
    for raw in ops:
        _apply_one(new, raw if isinstance(raw, Op) else Op.model_validate(raw))
    try:
        new = normalize(new)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    problems = protected_violations(normalize(config), new, charter) if enforce else []
    if problems:
        raise ProtectedViolation("; ".join(problems))
    return new


def diff(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured differences between two configs, ordered by path."""
    a, b = normalize(a), normalize(b)
    out: list[dict[str, Any]] = []

    def cmp(path: str, before: Any, after: Any) -> None:
        if before == after:
            return
        change = "added" if before is None else "removed" if after is None else "changed"
        out.append({"path": path, "change": change, "before": before, "after": after})

    for section in ("memory", "rules"):
        ia = {i["id"]: i for i in a[section]}
        ib = {i["id"]: i for i in b[section]}
        for key in sorted(ia.keys() | ib.keys()):
            cmp(f"{section}/{key}", ia.get(key), ib.get(key))
    for section in ("tool_policy", "workflow"):
        for key in sorted(a[section].keys() | b[section].keys()):
            cmp(f"{section}/{key}", a[section].get(key), b[section].get(key))
    return out
