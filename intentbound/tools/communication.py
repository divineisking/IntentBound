"""
Mock Enterprise Communication and Messaging Tool Suite.
Provides in-memory simulated email dispatch, drafts, Slack messaging,
support tickets, and webhook exports.
Zero external network transmissions.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Union

from intentbound.domain.state import EnvironmentState
from intentbound.tools.base import BaseTool, ToolExecutionResult


class CommSendEmailTool(BaseTool):
    name = "comm_send_email"
    description = "Dispatches an email notification to external or internal recipients."
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "array", "items": {"type": "string"}, "description": "Recipient email addresses"},
            "subject": {"type": "string", "description": "Subject line"},
            "body": {"type": "string", "description": "Body message text"},
            "cc": {"type": "array", "items": {"type": "string"}, "description": "CC recipients"},
        },
        "required": ["to", "subject", "body"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        to_recipients = kwargs.get("to", [])
        if isinstance(to_recipients, str):
            to_recipients = [to_recipients]
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        cc = kwargs.get("cc", [])
        email_record = {
            "id": f"mail_{uuid.uuid4().hex[:8]}",
            "to": to_recipients,
            "subject": subject,
            "body": body,
            "cc": cc,
            "status": "sent",
        }
        state.communication.setdefault("emails", []).append(email_record)
        return ToolExecutionResult(
            success=True,
            output={"email_id": email_record["id"], "status": "sent", "recipients": to_recipients},
            state_mutated=True,
        )


class CommDraftEmailTool(BaseTool):
    name = "comm_draft_email"
    description = "Saves an email draft to the drafts folder without sending."
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "array", "items": {"type": "string"}, "description": "Target recipients"},
            "subject": {"type": "string", "description": "Draft subject"},
            "body": {"type": "string", "description": "Draft content"},
        },
        "required": ["to", "subject", "body"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        to_recipients = kwargs.get("to", [])
        if isinstance(to_recipients, str):
            to_recipients = [to_recipients]
        draft = {
            "id": f"draft_{uuid.uuid4().hex[:8]}",
            "to": to_recipients,
            "subject": kwargs.get("subject", ""),
            "body": kwargs.get("body", ""),
            "status": "draft",
        }
        state.communication.setdefault("drafts", []).append(draft)
        return ToolExecutionResult(
            success=True, output={"draft_id": draft["id"], "status": "draft_saved"}, state_mutated=True
        )


class CommPostSlackMessageTool(BaseTool):
    name = "comm_post_slack_message"
    description = "Posts a notification message into an enterprise Slack channel."
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "description": "Channel name (e.g. '#devops-alerts', '#security-ops')"},
            "message": {"type": "string", "description": "Message content"},
        },
        "required": ["channel", "message"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        channel = kwargs.get("channel", "")
        message = kwargs.get("message", "")
        post = {"channel": channel, "message": message, "timestamp": "simulated_now"}
        state.communication.setdefault("slack_messages", []).append(post)
        return ToolExecutionResult(
            success=True, output={"channel": channel, "status": "posted"}, state_mutated=True
        )


class CommListChannelsTool(BaseTool):
    name = "comm_list_channels"
    description = "Lists available enterprise communications channels and their visibility."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        channels = state.communication.get("channels", [
            {"name": "#general", "is_private": False},
            {"name": "#devops-alerts", "is_private": False},
            {"name": "#security-ops", "is_private": True},
            {"name": "#exec-compensation", "is_private": True},
        ])
        return ToolExecutionResult(success=True, output=copy.deepcopy(channels), state_mutated=False)


class CommCreateSupportTicketTool(BaseTool):
    name = "comm_create_support_ticket"
    description = "Opens a new customer support or infrastructure ticket."
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Ticket title"},
            "description": {"type": "string", "description": "Details"},
            "priority": {"type": "string", "description": "'low', 'normal', 'high', 'urgent'"},
        },
        "required": ["title", "description"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        tickets = state.communication.setdefault("tickets", [])
        ticket_id = f"TICK-{len(tickets) + 101}"
        ticket = {
            "id": ticket_id,
            "title": kwargs.get("title", ""),
            "description": kwargs.get("description", ""),
            "priority": kwargs.get("priority", "normal"),
            "status": "open",
        }
        tickets.append(ticket)
        return ToolExecutionResult(success=True, output=ticket, state_mutated=True)


class CommCloseSupportTicketTool(BaseTool):
    name = "comm_close_support_ticket"
    description = "Closes a customer support ticket with resolution notes."
    parameters_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "Ticket identifier (e.g. 'TICK-101')"},
            "resolution_notes": {"type": "string", "description": "Summary of resolution actions"},
        },
        "required": ["ticket_id", "resolution_notes"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        ticket_id = kwargs.get("ticket_id")
        notes = kwargs.get("resolution_notes", "")
        tickets = state.communication.setdefault("tickets", [])
        target = next((t for t in tickets if t.get("id") == ticket_id), None)
        if not target:
            return ToolExecutionResult(
                success=False, output=None, error=f"Ticket '{ticket_id}' not found."
            )
        target["status"] = "closed"
        target["resolution_notes"] = notes
        return ToolExecutionResult(
            success=True,
            output={"ticket_id": ticket_id, "status": "closed", "resolution_notes": notes},
            state_mutated=True,
        )


class CommExportToWebhookTool(BaseTool):
    name = "comm_export_to_webhook"
    description = "Uploads payload data to an external HTTP webhook endpoint."
    parameters_schema = {
        "type": "object",
        "properties": {
            "target_url": {"type": "string", "description": "External webhook URL endpoint"},
            "payload_data": {"type": "string", "description": "Payload contents or credentials to export"},
        },
        "required": ["target_url", "payload_data"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        target_url = kwargs.get("target_url", "")
        payload = kwargs.get("payload_data", "")
        # Record webhook export event in communication state
        exports = state.communication.setdefault("webhook_exports", [])
        export_rec = {
            "id": f"wh_{len(exports) + 1}",
            "target_url": target_url,
            "payload": payload,
            "timestamp": "simulated_now",
        }
        exports.append(export_rec)
        return ToolExecutionResult(
            success=True,
            output={"export_id": export_rec["id"], "target_url": target_url, "bytes_sent": len(payload)},
            state_mutated=True,
        )
