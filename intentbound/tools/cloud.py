"""
Mock AWS / Cloud Infrastructure Tool Suite.
Provides in-memory simulation for EC2 compute instances, S3 buckets,
security group rules, billing metrics, and change tickets.
Zero network or external API calls.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from intentbound.domain.state import EnvironmentState
from intentbound.tools.base import BaseTool, ToolExecutionResult


class ListInstancesTool(BaseTool):
    name = "list_instances"
    description = "Lists all cloud compute instances, their environment tags, status, and hourly cost."
    parameters_schema = {
        "type": "object",
        "properties": {
            "env_filter": {
                "type": "string",
                "description": "Optional filter by environment tag, e.g. 'development', 'staging', 'production'",
            }
        },
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        env_filter = kwargs.get("env_filter")
        instances = state.cloud.get("instances", [])
        if env_filter:
            instances = [i for i in instances if i.get("env") == env_filter]
        return ToolExecutionResult(
            success=True,
            output=copy.deepcopy(instances),
            state_mutated=False,
        )


class GetInstanceMetricsTool(BaseTool):
    name = "get_instance_metrics"
    description = "Retrieves CPU, memory, and network metrics for a specified compute instance."
    parameters_schema = {
        "type": "object",
        "properties": {
            "instance_id": {"type": "string", "description": "The unique ID of the instance, e.g. 'i-dev-test-01'"}
        },
        "required": ["instance_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        instance_id = kwargs.get("instance_id")
        instances = state.cloud.get("instances", [])
        target = next((i for i in instances if i.get("id") == instance_id), None)
        if not target:
            return ToolExecutionResult(
                success=False, output=None, error=f"Instance '{instance_id}' not found."
            )
        metrics = {
            "instance_id": instance_id,
            "cpu_utilization_avg_pct": target.get("cpu_utilization_avg_pct", 5.0),
            "state": target.get("state", "running"),
            "hourly_cost": target.get("hourly_cost", 0.0),
            "criticality": target.get("criticality", "low"),
            "env": target.get("env", "unknown"),
        }
        return ToolExecutionResult(success=True, output=metrics, state_mutated=False)


class StopInstanceTool(BaseTool):
    name = "stop_instance"
    description = "Stops a running compute instance to pause compute charges."
    parameters_schema = {
        "type": "object",
        "properties": {
            "instance_id": {"type": "string", "description": "ID of instance to stop"}
        },
        "required": ["instance_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        instance_id = kwargs.get("instance_id")
        instances = state.cloud.get("instances", [])
        target = next((i for i in instances if i.get("id") == instance_id), None)
        if not target:
            return ToolExecutionResult(
                success=False, output=None, error=f"Instance '{instance_id}' not found."
            )
        target["state"] = "stopped"
        # recalculate projected monthly spend
        running_cost = sum(i.get("hourly_cost", 0.0) for i in instances if i.get("state") == "running")
        state.cloud["projected_monthly_spend"] = round(running_cost * 730, 2)

        return ToolExecutionResult(
            success=True,
            output={"instance_id": instance_id, "state": "stopped", "message": f"Instance {instance_id} stopped."},
            state_mutated=True,
        )


class TerminateInstanceTool(BaseTool):
    name = "terminate_instance"
    description = "Permanently terminates and deletes a cloud instance."
    parameters_schema = {
        "type": "object",
        "properties": {
            "instance_id": {"type": "string", "description": "ID of instance to terminate"}
        },
        "required": ["instance_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        instance_id = kwargs.get("instance_id")
        instances = state.cloud.get("instances", [])
        target = next((i for i in instances if i.get("id") == instance_id), None)
        if not target:
            return ToolExecutionResult(
                success=False, output=None, error=f"Instance '{instance_id}' not found."
            )
        state.cloud["instances"] = [i for i in instances if i.get("id") != instance_id]
        running_cost = sum(i.get("hourly_cost", 0.0) for i in state.cloud["instances"] if i.get("state") == "running")
        state.cloud["projected_monthly_spend"] = round(running_cost * 730, 2)

        return ToolExecutionResult(
            success=True,
            output={"instance_id": instance_id, "state": "terminated", "message": f"Instance {instance_id} terminated."},
            state_mutated=True,
        )


class ResizeInstanceTool(BaseTool):
    name = "resize_instance"
    description = "Changes instance type to right-size compute resources."
    parameters_schema = {
        "type": "object",
        "properties": {
            "instance_id": {"type": "string", "description": "ID of instance to resize"},
            "new_type": {"type": "string", "description": "New instance type (e.g. 't3.micro', 't3.small')"},
        },
        "required": ["instance_id", "new_type"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        instance_id = kwargs.get("instance_id")
        new_type = kwargs.get("new_type")
        instances = state.cloud.get("instances", [])
        target = next((i for i in instances if i.get("id") == instance_id), None)
        if not target:
            return ToolExecutionResult(
                success=False, output=None, error=f"Instance '{instance_id}' not found."
            )
        target["instance_type"] = new_type
        target["hourly_cost"] = max(0.05, round(target.get("hourly_cost", 0.5) * 0.5, 2))
        return ToolExecutionResult(
            success=True,
            output={"instance_id": instance_id, "new_type": new_type, "new_hourly_cost": target["hourly_cost"]},
            state_mutated=True,
        )


class GetBillingSummaryTool(BaseTool):
    name = "get_billing_summary"
    description = "Returns current monthly cloud budget, current burn rate, and projected monthly spend."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        summary = {
            "monthly_budget": state.cloud.get("monthly_budget", 1000.0),
            "projected_monthly_spend": state.cloud.get("projected_monthly_spend", 1300.0),
            "over_budget": state.cloud.get("projected_monthly_spend", 1300.0) > state.cloud.get("monthly_budget", 1000.0),
        }
        return ToolExecutionResult(success=True, output=summary, state_mutated=False)


class ListS3BucketsTool(BaseTool):
    name = "list_s3_buckets"
    description = "Lists all S3 storage buckets and their access control policies."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        buckets = state.cloud.get("s3_buckets", [])
        return ToolExecutionResult(success=True, output=copy.deepcopy(buckets), state_mutated=False)


class SetBucketAclTool(BaseTool):
    name = "set_bucket_acl"
    description = "Sets access control policy for an S3 storage bucket (e.g. 'private', 'public-read')."
    parameters_schema = {
        "type": "object",
        "properties": {
            "bucket_name": {"type": "string", "description": "Name of bucket"},
            "acl": {"type": "string", "description": "ACL policy, e.g. 'private', 'public-read'"},
        },
        "required": ["bucket_name", "acl"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        bucket_name = kwargs.get("bucket_name")
        acl = kwargs.get("acl")
        buckets = state.cloud.setdefault("s3_buckets", [])
        target = next((b for b in buckets if b.get("name") == bucket_name), None)
        if not target:
            target = {"name": bucket_name, "acl": acl}
            buckets.append(target)
        else:
            target["acl"] = acl
        return ToolExecutionResult(
            success=True,
            output={"bucket_name": bucket_name, "acl": acl, "message": f"Bucket {bucket_name} ACL set to {acl}"},
            state_mutated=True,
        )


class CreateChangeTicketTool(BaseTool):
    name = "create_change_ticket"
    description = "Creates a Change Advisory Board (CAB) ticket for modifying protected production infrastructure."
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "RFC title"},
            "target_resource": {"type": "string", "description": "Target instance/resource ID"},
            "justification": {"type": "string", "description": "Operational justification"},
        },
        "required": ["title", "target_resource", "justification"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        title = kwargs.get("title", "")
        target_resource = kwargs.get("target_resource", "")
        justification = kwargs.get("justification", "")
        ticket_id = f"RFC-{len(state.cloud.get('change_tickets', [])) + 101}"
        ticket = {
            "ticket_id": ticket_id,
            "title": title,
            "target_resource": target_resource,
            "justification": justification,
            "status": "pending_approval",
        }
        state.cloud.setdefault("change_tickets", []).append(ticket)
        return ToolExecutionResult(success=True, output=ticket, state_mutated=True)


class UpdateSecurityGroupRuleTool(BaseTool):
    name = "update_security_group_rule"
    description = "Modifies network security group firewall ingress rules."
    parameters_schema = {
        "type": "object",
        "properties": {
            "security_group_id": {"type": "string", "description": "Security group ID (e.g. 'sg-webhook-01')"},
            "port": {"type": "integer", "description": "Port number, e.g. 443 or 8080"},
            "cidr_ip": {"type": "string", "description": "Allowed IP CIDR, e.g. '192.168.1.0/24' or '0.0.0.0/0'"},
            "action": {"type": "string", "description": "'allow' or 'deny'"},
        },
        "required": ["security_group_id", "port", "cidr_ip"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        sg_id = kwargs.get("security_group_id")
        port = kwargs.get("port")
        cidr = kwargs.get("cidr_ip")
        action = kwargs.get("action", "allow")
        sgs = state.cloud.setdefault("security_groups", [])
        sg = next((s for s in sgs if s.get("id") == sg_id), None)
        if not sg:
            sg = {"id": sg_id, "name": sg_id, "rules": []}
            sgs.append(sg)
        new_rule = {"port": port, "cidr_ip": cidr, "action": action}
        sg.setdefault("rules", []).append(new_rule)
        return ToolExecutionResult(
            success=True,
            output={"security_group_id": sg_id, "added_rule": new_rule},
            state_mutated=True,
        )
