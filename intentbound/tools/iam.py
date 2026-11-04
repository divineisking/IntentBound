"""
Mock Identity & Access Management (IAM) Tool Suite.
Provides in-memory simulation for user management, role assignments,
API keys, multi-factor authentication (MFA), and audit logging.
Zero external directory or identity provider calls.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from intentbound.domain.state import EnvironmentState
from intentbound.tools.base import BaseTool, ToolExecutionResult


class IamListUsersTool(BaseTool):
    name = "iam_list_users"
    description = "Lists enterprise user profiles, department, status, active roles, and MFA state."
    parameters_schema = {
        "type": "object",
        "properties": {
            "name_filter": {"type": "string", "description": "Optional search string for user display name"}
        },
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        name_filter = kwargs.get("name_filter")
        users = state.iam.get("users", [])
        if name_filter:
            users = [u for u in users if name_filter.lower() in u.get("name", "").lower()]
        return ToolExecutionResult(success=True, output=copy.deepcopy(users), state_mutated=False)


class IamGetUserRolesTool(BaseTool):
    name = "iam_get_user_roles"
    description = "Retrieves active assigned roles and associated permission scopes for a user ID."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Unique user ID (e.g. 'usr_101')"}
        },
        "required": ["user_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        user_id = kwargs.get("user_id", "")
        users = state.iam.get("users", [])
        target = next((u for u in users if u.get("id") == user_id), None)
        if not target:
            return ToolExecutionResult(success=False, output=None, error=f"User '{user_id}' not found.")
        return ToolExecutionResult(
            success=True,
            output={"user_id": user_id, "roles": copy.deepcopy(target.get("roles", []))},
            state_mutated=False,
        )


class IamAssignRoleTool(BaseTool):
    name = "iam_assign_role"
    description = "Assigns an IAM role to a user profile."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Target user ID"},
            "role_id": {"type": "string", "description": "Role ID to assign, e.g. 'viewer' or 'exec_comp_reader'"},
        },
        "required": ["user_id", "role_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        user_id = kwargs.get("user_id", "")
        role_id = kwargs.get("role_id", "")
        users = state.iam.setdefault("users", [])
        target = next((u for u in users if u.get("id") == user_id), None)
        if not target:
            return ToolExecutionResult(success=False, output=None, error=f"User '{user_id}' not found.")
        roles = target.setdefault("roles", [])
        if role_id not in roles:
            roles.append(role_id)
        # Log to audit trail
        state.iam.setdefault("audit_log", []).append({
            "action": "iam_assign_role",
            "user_id": user_id,
            "role_id": role_id,
            "timestamp": "simulated_now",
        })
        return ToolExecutionResult(
            success=True,
            output={"user_id": user_id, "assigned_role": role_id, "current_roles": roles},
            state_mutated=True,
        )


class IamRevokeRoleTool(BaseTool):
    name = "iam_revoke_role"
    description = "Revokes an IAM role from a user."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Target user ID"},
            "role_id": {"type": "string", "description": "Role ID to revoke"},
        },
        "required": ["user_id", "role_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        user_id = kwargs.get("user_id", "")
        role_id = kwargs.get("role_id", "")
        users = state.iam.get("users", [])
        target = next((u for u in users if u.get("id") == user_id), None)
        if not target:
            return ToolExecutionResult(success=False, output=None, error=f"User '{user_id}' not found.")
        roles = target.get("roles", [])
        if role_id in roles:
            roles.remove(role_id)
        state.iam.setdefault("audit_log", []).append({
            "action": "iam_revoke_role",
            "user_id": user_id,
            "role_id": role_id,
            "timestamp": "simulated_now",
        })
        return ToolExecutionResult(
            success=True,
            output={"user_id": user_id, "revoked_role": role_id, "current_roles": roles},
            state_mutated=True,
        )


class IamCreateApiKeyTool(BaseTool):
    name = "iam_create_api_key"
    description = "Generates a new programmatic API key for a specified service."
    parameters_schema = {
        "type": "object",
        "properties": {
            "service_name": {"type": "string", "description": "Service name"},
            "scope": {"type": "array", "items": {"type": "string"}, "description": "Allowed permission scopes"},
        },
        "required": ["service_name", "scope"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        service = kwargs.get("service_name", "")
        scope = kwargs.get("scope", [])
        key_id = f"ak_{uuid.uuid4().hex[:12]}"
        key_record = {"key_id": key_id, "service": service, "scope": scope, "active": True}
        state.iam.setdefault("api_keys", []).append(key_record)
        return ToolExecutionResult(
            success=True, output={"key_id": key_id, "service": service, "scope": scope}, state_mutated=True
        )


class IamDeactivateUserTool(BaseTool):
    name = "iam_deactivate_user"
    description = "Deactivates an enterprise user account, revoking active sessions."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Unique user ID to deactivate"}
        },
        "required": ["user_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        user_id = kwargs.get("user_id", "")
        users = state.iam.get("users", [])
        target = next((u for u in users if u.get("id") == user_id), None)
        if not target:
            return ToolExecutionResult(success=False, output=None, error=f"User '{user_id}' not found.")
        target["active"] = False
        target["status"] = "deactivated"
        state.iam.setdefault("audit_log", []).append({
            "action": "iam_deactivate_user",
            "user_id": user_id,
            "timestamp": "simulated_now",
        })
        return ToolExecutionResult(
            success=True,
            output={"user_id": user_id, "active": False, "status": "deactivated"},
            state_mutated=True,
        )


class IamModifyMfaTool(BaseTool):
    name = "iam_modify_mfa"
    description = "Enables or disables Multi-Factor Authentication (MFA) for a user account."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Target user ID"},
            "enabled": {"type": "boolean", "description": "Whether MFA should be enabled or disabled"},
        },
        "required": ["user_id", "enabled"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        user_id = kwargs.get("user_id", "")
        enabled = kwargs.get("enabled", True)
        users = state.iam.get("users", [])
        target = next((u for u in users if u.get("id") == user_id), None)
        if not target:
            return ToolExecutionResult(success=False, output=None, error=f"User '{user_id}' not found.")
        target["mfa_enabled"] = enabled
        state.iam.setdefault("audit_log", []).append({
            "action": "iam_modify_mfa",
            "user_id": user_id,
            "mfa_enabled": enabled,
            "timestamp": "simulated_now",
        })
        return ToolExecutionResult(
            success=True,
            output={"user_id": user_id, "mfa_enabled": enabled},
            state_mutated=True,
        )


class IamGetAuditLogTool(BaseTool):
    name = "iam_get_audit_log"
    description = "Retrieves the immutable audit log of authentication and authorization events."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        logs = state.iam.get("audit_log", [])
        return ToolExecutionResult(success=True, output=copy.deepcopy(logs), state_mutated=False)
