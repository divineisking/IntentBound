"""
EnvironmentState Container and StateDiffEngine.
Provides deepcopy-isolated, snapshotable in-memory runtime state and recursive
structural diffing across cloud, database, filesystem, communication, and IAM domains.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class StateDiff:
    """Represents the structured differences between two environment states."""
    added: Dict[str, Any] = field(default_factory=dict)
    modified: Dict[str, Any] = field(default_factory=dict)
    deleted: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, int] = field(default_factory=dict)

    @property
    def has_mutations(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "summary": self.summary,
            "has_mutations": self.has_mutations,
        }


class EnvironmentState:
    """
    Isolated in-memory state container partitioned by enterprise domain.
    All tool interactions operate strictly on this in-memory object with zero external side effects.
    """

    CORE_DOMAINS = ("cloud", "database", "filesystem", "communication", "iam", "metadata")

    def __init__(
        self,
        cloud: Optional[Dict[str, Any]] = None,
        database: Optional[Dict[str, Any]] = None,
        filesystem: Optional[Dict[str, Any]] = None,
        communication: Optional[Dict[str, Any]] = None,
        iam: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.cloud: Dict[str, Any] = copy.deepcopy(cloud or {})
        self.database: Dict[str, Any] = copy.deepcopy(database or {})
        self.filesystem: Dict[str, Any] = copy.deepcopy(filesystem or {})
        self.communication: Dict[str, Any] = copy.deepcopy(communication or {})
        self.iam: Dict[str, Any] = copy.deepcopy(iam or {})
        self.metadata: Dict[str, Any] = copy.deepcopy(metadata or {})
        self._extra: Dict[str, Any] = copy.deepcopy(kwargs)
        self._snapshot_stack: List[Dict[str, Any]] = []

    def clone(self) -> "EnvironmentState":
        """Creates a completely independent, deep-copied replica of current state."""
        return EnvironmentState.from_dict(self.to_dict())

    def snapshot(self) -> None:
        """Pushes current state onto snapshot stack for rollback support."""
        self._snapshot_stack.append(self.to_dict())

    def rollback(self) -> bool:
        """Restores state from the most recent snapshot. Returns False if stack empty."""
        if not self._snapshot_stack:
            return False
        previous = self._snapshot_stack.pop()
        self.reset(previous)
        return True

    def reset(self, new_state: Union[Dict[str, Any], "EnvironmentState"]) -> None:
        """Resets the environment state to specified data."""
        if isinstance(new_state, EnvironmentState):
            d = new_state.to_dict()
        else:
            d = new_state

        self.cloud = copy.deepcopy(d.get("cloud", {}))
        self.database = copy.deepcopy(d.get("database", {}))
        self.filesystem = copy.deepcopy(d.get("filesystem", {}))
        self.communication = copy.deepcopy(d.get("communication", {}))
        self.iam = copy.deepcopy(d.get("iam", {}))
        self.metadata = copy.deepcopy(d.get("metadata", {}))
        self._extra = {k: copy.deepcopy(v) for k, v in d.items() if k not in self.CORE_DOMAINS}

    def to_dict(self) -> Dict[str, Any]:
        """Serializes environment state to standard dictionary."""
        d = {
            "cloud": copy.deepcopy(self.cloud),
            "database": copy.deepcopy(self.database),
            "filesystem": copy.deepcopy(self.filesystem),
            "communication": copy.deepcopy(self.communication),
            "iam": copy.deepcopy(self.iam),
            "metadata": copy.deepcopy(self.metadata),
        }
        for k, v in self._extra.items():
            d[k] = copy.deepcopy(v)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentState":
        """Instantiates state container from a dictionary."""
        return cls(
            cloud=data.get("cloud"),
            database=data.get("database"),
            filesystem=data.get("filesystem"),
            communication=data.get("communication"),
            iam=data.get("iam"),
            metadata=data.get("metadata"),
            **{k: v for k, v in data.items() if k not in cls.CORE_DOMAINS},
        )

    # Dictionary-like subscript access for backwards compatibility and ease of use
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item) and item in self.CORE_DOMAINS:
            return getattr(self, item)
        if item in self._extra:
            return self._extra[item]
        raise KeyError(f"Domain '{item}' not found in EnvironmentState.")

    def __setitem__(self, item: str, value: Any) -> None:
        if item in self.CORE_DOMAINS:
            setattr(self, item, value)
        else:
            self._extra[item] = value

    def __contains__(self, item: str) -> bool:
        return item in self.CORE_DOMAINS or item in self._extra

    def get(self, item: str, default: Any = None) -> Any:
        if hasattr(self, item) and item in self.CORE_DOMAINS:
            return getattr(self, item)
        return self._extra.get(item, default)


class StateDiffEngine:
    """
    Computes fine-grained recursive structural diffs between two states.
    Tracks additions, deletions, modifications, and domain mutation counts.
    """

    @classmethod
    def compute_diff(
        cls,
        before: Union[EnvironmentState, Dict[str, Any]],
        after: Union[EnvironmentState, Dict[str, Any]],
    ) -> StateDiff:
        d_before = before.to_dict() if isinstance(before, EnvironmentState) else before
        d_after = after.to_dict() if isinstance(after, EnvironmentState) else after

        added: Dict[str, Any] = {}
        modified: Dict[str, Any] = {}
        deleted: Dict[str, Any] = {}
        summary: Dict[str, int] = {}

        all_domains = set(d_before.keys()).union(set(d_after.keys()))

        for domain in all_domains:
            if domain == "metadata":
                continue  # skip execution timestamps and transient run metadata
            dom_before = d_before.get(domain, {})
            dom_after = d_after.get(domain, {})

            dom_added, dom_mod, dom_del = cls._diff_recursive(dom_before, dom_after, path=domain)
            if dom_added:
                added[domain] = dom_added
            if dom_mod:
                modified[domain] = dom_mod
            if dom_del:
                deleted[domain] = dom_del

            mutation_count = len(dom_added) + len(dom_mod) + len(dom_del)
            if mutation_count > 0:
                summary[domain] = mutation_count

        summary["total_mutations"] = sum(summary.values())
        return StateDiff(added=added, modified=modified, deleted=deleted, summary=summary)

    @classmethod
    def _diff_recursive(
        cls, val_before: Any, val_after: Any, path: str
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        added: Dict[str, Any] = {}
        modified: Dict[str, Any] = {}
        deleted: Dict[str, Any] = {}

        if isinstance(val_before, dict) and isinstance(val_after, dict):
            b_keys = set(val_before.keys())
            a_keys = set(val_after.keys())

            for k in a_keys - b_keys:
                added[k] = val_after[k]
            for k in b_keys - a_keys:
                deleted[k] = val_before[k]
            for k in b_keys & a_keys:
                if val_before[k] != val_after[k]:
                    if isinstance(val_before[k], dict) and isinstance(val_after[k], dict):
                        sub_add, sub_mod, sub_del = cls._diff_recursive(
                            val_before[k], val_after[k], f"{path}.{k}"
                        )
                        if sub_add or sub_mod or sub_del:
                            modified[k] = {"added": sub_add, "modified": sub_mod, "deleted": sub_del}
                    elif isinstance(val_before[k], list) and isinstance(val_after[k], list):
                        list_diff = cls._diff_lists(val_before[k], val_after[k])
                        if list_diff:
                            modified[k] = list_diff
                    else:
                        modified[k] = {"before": val_before[k], "after": val_after[k]}

        elif isinstance(val_before, list) and isinstance(val_after, list):
            list_diff = cls._diff_lists(val_before, val_after)
            if list_diff:
                modified["items"] = list_diff
        elif val_before != val_after:
            modified["value"] = {"before": val_before, "after": val_after}

        return added, modified, deleted

    @classmethod
    def _diff_lists(cls, list_before: List[Any], list_after: List[Any]) -> Dict[str, Any]:
        """Compares two lists, handling dictionary elements with 'id' or 'name' keys."""
        if list_before == list_after:
            return {}

        # If items are dicts with 'id' or 'name', track by identifier
        b_keyed = {}
        for idx, item in enumerate(list_before):
            if isinstance(item, dict) and ("id" in item or "name" in item):
                key = item.get("id") or item.get("name")
                b_keyed[key] = item
            else:
                b_keyed[f"idx_{idx}"] = item

        a_keyed = {}
        for idx, item in enumerate(list_after):
            if isinstance(item, dict) and ("id" in item or "name" in item):
                key = item.get("id") or item.get("name")
                a_keyed[key] = item
            else:
                a_keyed[f"idx_{idx}"] = item

        b_ids = set(b_keyed.keys())
        a_ids = set(a_keyed.keys())

        added = [a_keyed[i] for i in a_ids - b_ids]
        removed = [b_keyed[i] for i in b_ids - a_ids]
        changed = []

        for common in b_ids & a_ids:
            if b_keyed[common] != a_keyed[common]:
                changed.append({"id": common, "before": b_keyed[common], "after": a_keyed[common]})

        diff: Dict[str, Any] = {}
        if added:
            diff["added_elements"] = added
        if removed:
            diff["removed_elements"] = removed
        if changed:
            diff["changed_elements"] = changed
        if not diff and list_before != list_after:
            diff["before"] = list_before
            diff["after"] = list_after
        return diff
