"""
Mock Hierarchical Virtual Filesystem Tool Suite.
Provides in-memory simulated file reading, writing, deletion, searching,
permission updating (chmod), and defensive quarantine.
Zero external disk I/O.
"""

from __future__ import annotations

import copy
import fnmatch
from typing import Any, Dict, List, Optional

from intentbound.domain.state import EnvironmentState
from intentbound.tools.base import BaseTool, ToolExecutionResult


class FsListDirectoryTool(BaseTool):
    name = "fs_list_directory"
    description = "Lists files and subdirectories located at the specified virtual path."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute virtual directory path, e.g. '/var/log' or '/tmp'"}
        },
        "required": ["path"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        dir_path = kwargs.get("path", "/").rstrip("/") or "/"
        files_map = state.filesystem.get("files", {})
        results = []

        for f_path, meta in files_map.items():
            if f_path == dir_path:
                continue
            parent = "/".join(f_path.rstrip("/").split("/")[:-1]) or "/"
            if parent == dir_path:
                results.append({
                    "path": f_path,
                    "name": f_path.split("/")[-1],
                    "size": meta.get("size", len(meta.get("content", ""))),
                    "permissions": meta.get("permissions", "644"),
                    "is_dir": meta.get("is_dir", False),
                    "is_backup": meta.get("is_backup", False),
                    "tags": meta.get("tags", []),
                })

        return ToolExecutionResult(success=True, output=results, state_mutated=False)


class FsReadFileTool(BaseTool):
    name = "fs_read_file"
    description = "Reads and returns the string content of a virtual file."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file"}
        },
        "required": ["path"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path", "")
        files_map = state.filesystem.get("files", {})
        if path not in files_map:
            return ToolExecutionResult(
                success=False, output=None, error=f"File not found: '{path}'"
            )
        entry = files_map[path]
        if entry.get("is_dir"):
            return ToolExecutionResult(
                success=False, output=None, error=f"'{path}' is a directory, not a file."
            )
        return ToolExecutionResult(
            success=True, output=entry.get("content", ""), state_mutated=False
        )


class FsWriteFileTool(BaseTool):
    name = "fs_write_file"
    description = "Writes text content to a virtual file, creating it if it does not exist."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target absolute path"},
            "content": {"type": "string", "description": "Text content to write"},
            "overwrite": {"type": "boolean", "description": "Allow overwriting existing file"},
        },
        "required": ["path", "content"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        overwrite = kwargs.get("overwrite", True)
        files_map = state.filesystem.setdefault("files", {})

        if path in files_map and not overwrite:
            return ToolExecutionResult(
                success=False, output=None, error=f"File '{path}' already exists and overwrite=False."
            )

        files_map[path] = {
            "content": content,
            "size": len(content),
            "permissions": "644",
            "is_dir": False,
        }
        return ToolExecutionResult(
            success=True,
            output={"path": path, "size": len(content), "message": "File written successfully."},
            state_mutated=True,
        )


class FsDeleteFileTool(BaseTool):
    name = "fs_delete_file"
    description = "Deletes a virtual file from the simulated filesystem."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target path to delete"}
        },
        "required": ["path"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path", "")
        files_map = state.filesystem.get("files", {})
        if path not in files_map:
            return ToolExecutionResult(
                success=False, output=None, error=f"Cannot delete non-existent file: '{path}'"
            )
        deleted_entry = files_map.pop(path)
        return ToolExecutionResult(
            success=True,
            output={
                "deleted_path": path,
                "was_backup": deleted_entry.get("is_backup", False),
                "message": f"File '{path}' deleted.",
            },
            state_mutated=True,
        )


class FsSearchFilesTool(BaseTool):
    name = "fs_search_files"
    description = "Searches for virtual files matching a glob pattern (e.g. '*.log', '*backup*')."
    parameters_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob search pattern"},
            "base_path": {"type": "string", "description": "Base directory to search under (default '/')"},
        },
        "required": ["pattern"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        pattern = kwargs.get("pattern", "*")
        base_path = kwargs.get("base_path", "/").rstrip("/") or "/"
        files_map = state.filesystem.get("files", {})
        matches = []
        for p, meta in files_map.items():
            if p.startswith(base_path) and fnmatch.fnmatch(p.split("/")[-1], pattern):
                matches.append({"path": p, "size": meta.get("size", len(meta.get("content", "")))})
        return ToolExecutionResult(success=True, output=matches, state_mutated=False)


class FsChmodTool(BaseTool):
    name = "fs_chmod"
    description = "Changes POSIX permissions mode on a virtual file or directory (e.g. '600', '777')."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target path"},
            "mode": {"type": "string", "description": "Octal permissions string (e.g. '600', '755')"},
        },
        "required": ["path", "mode"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path", "")
        mode = kwargs.get("mode", "644")
        files_map = state.filesystem.get("files", {})
        if path not in files_map:
            return ToolExecutionResult(
                success=False, output=None, error=f"Cannot chmod non-existent file: '{path}'"
            )
        files_map[path]["permissions"] = mode
        return ToolExecutionResult(
            success=True,
            output={"path": path, "permissions": mode, "message": f"Permissions set to {mode}"},
            state_mutated=True,
        )


class FsQuarantineFileTool(BaseTool):
    name = "fs_quarantine_file"
    description = "Isolates a suspicious binary or script by moving it to an encrypted /quarantine directory and stripping execution bits."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to isolate/quarantine"},
            "quarantine_dir": {"type": "string", "description": "Destination directory (default '/quarantine')"},
        },
        "required": ["path"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path", "")
        quarantine_dir = kwargs.get("quarantine_dir", "/quarantine").rstrip("/")
        files_map = state.filesystem.setdefault("files", {})
        if path not in files_map:
            return ToolExecutionResult(
                success=False, output=None, error=f"File '{path}' not found."
            )
        file_obj = files_map.pop(path)
        file_name = path.split("/")[-1]
        dest_path = f"{quarantine_dir}/{file_name}.quarantine"
        file_obj["permissions"] = "000"
        file_obj["is_quarantined"] = True
        files_map[dest_path] = file_obj
        return ToolExecutionResult(
            success=True,
            output={"original_path": path, "quarantine_path": dest_path, "status": "quarantined"},
            state_mutated=True,
        )
