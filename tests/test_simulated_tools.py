"""Tests for IntentBound simulated tool suites, ToolRegistry, and ActionLogger.

Tier 1: Feature Coverage (5 domain tool suites: Cloud, DB, FS, Comm, IAM)
Tier 2: Boundary & Corner Cases (Missing arguments, non-existent entities, empty state)
Tier 3: Cross-Feature Combinations (Tool execution -> Action logging -> State mutation)
"""

from __future__ import annotations

import copy
import unittest
from typing import Any, Dict

try:
    from intentbound.domain.state import EnvironmentState
    from intentbound.tools import (
        ActionLogger,
        BaseTool,
        CommDraftEmailTool,
        CommListChannelsTool,
        CommPostSlackMessageTool,
        CommSendEmailTool,
        DbCreateBackupTool,
        DbExecuteQueryTool,
        DbGetTableSchemaTool,
        DbListTablesTool,
        DbRestoreBackupTool,
        FsChmodTool,
        FsDeleteFileTool,
        FsListDirectoryTool,
        FsReadFileTool,
        FsSearchFilesTool,
        FsWriteFileTool,
        GetBillingSummaryTool,
        IamAssignRoleTool,
        IamCreateApiKeyTool,
        IamGetAuditLogTool,
        IamGetUserRolesTool,
        IamListUsersTool,
        IamRevokeRoleTool,
        ListInstancesTool,
        SetBucketAclTool,
        StopInstanceTool,
        TerminateInstanceTool,
        ToolExecutionResult,
        ToolRegistry,
        create_default_tool_registry,
    )
    HAS_TOOLS_MODULE = True
except ImportError:
    HAS_TOOLS_MODULE = False

from tests.conftest import get_sample_environment_state


@unittest.skipUnless(HAS_TOOLS_MODULE, "intentbound.tools not yet available")
class TestSimulatedTools(unittest.TestCase):
    """Tier 1, Tier 2, and Tier 3 tests for all 5 simulated tool suites and registry."""

    def setUp(self) -> None:
        self.state_dict = get_sample_environment_state()
        self.env_state = EnvironmentState(
            cloud=copy.deepcopy(self.state_dict["cloud"]),
            database=copy.deepcopy(self.state_dict["database"]),
            filesystem=copy.deepcopy(self.state_dict["filesystem"]),
            communication=copy.deepcopy(self.state_dict["communication"]),
            iam=copy.deepcopy(self.state_dict["iam"]),
            metadata=copy.deepcopy(self.state_dict["metadata"]),
        )
        self.logger = ActionLogger()

    # -------------------------------------------------------------------------
    # BaseTool, ToolRegistry & ActionLogger Tests
    # -------------------------------------------------------------------------

    def test_tool_registry_registration_and_retrieval(self) -> None:
        """Tests that tools can be registered and retrieved by name from ToolRegistry."""
        registry = ToolRegistry()
        tool = ListInstancesTool()
        registry.register(tool)
        retrieved = registry.get("list_instances")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "list_instances")

    def test_default_tool_registry_contains_all_domains(self) -> None:
        """Tests create_default_tool_registry registers tools across all 5 domains."""
        registry = create_default_tool_registry()
        tool_names = registry.list_tools()
        self.assertGreaterEqual(len(tool_names), 25)
        # Check cloud, db, fs, comm, iam presence
        self.assertIn("list_instances", tool_names)
        self.assertIn("db_list_tables", tool_names)
        self.assertIn("fs_read_file", tool_names)
        self.assertIn("comm_send_email", tool_names)
        self.assertIn("iam_list_users", tool_names)

    def test_tool_registry_openai_schema_export(self) -> None:
        """Tests that ToolRegistry exports tools conforming to OpenAI tool schemas."""
        registry = ToolRegistry()
        registry.register(StopInstanceTool())
        schemas = registry.get_schemas()
        self.assertEqual(len(schemas), 1)
        self.assertIn("function", schemas[0])
        self.assertEqual(schemas[0]["function"]["name"], "stop_instance")
        self.assertIn("parameters", schemas[0]["function"])

    def test_action_logger_appends_records(self) -> None:
        """Tests ActionLogger records chronological action entries with authorization."""
        self.logger.log(
            tool_name="list_instances",
            arguments={},
            result="2 instances found",
            authorized=True,
            state_diff={},
        )
        self.logger.log(
            tool_name="stop_instance",
            arguments={"instance_id": "i-dev-01"},
            result={"status": "stopped"},
            authorized=True,
            state_diff={"modified": {"instances": 1}},
        )
        history = self.logger.records
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].step, 1)
        self.assertEqual(history[1].step, 2)
        self.assertEqual(history[1].tool_name, "stop_instance")

    # -------------------------------------------------------------------------
    # Suite 1: Cloud Tools
    # -------------------------------------------------------------------------

    def test_cloud_list_instances(self) -> None:
        """Tests list_instances returns all mock compute instances."""
        tool = ListInstancesTool()
        result = tool.execute(self.env_state)
        self.assertTrue(result.success)
        self.assertEqual(len(result.output), 2)
        instance_ids = [inst["id"] for inst in result.output]
        self.assertIn("i-dev-01", instance_ids)
        self.assertIn("i-prod-01", instance_ids)

    def test_cloud_stop_instance_mutates_state(self) -> None:
        """Tests stop_instance mutates target instance state to 'stopped'."""
        tool = StopInstanceTool()
        result = tool.execute(self.env_state, instance_id="i-dev-01")
        self.assertTrue(result.success)
        target = next(i for i in self.env_state.cloud["instances"] if i["id"] == "i-dev-01")
        self.assertEqual(target["state"], "stopped")

    def test_cloud_stop_instance_nonexistent_returns_error(self) -> None:
        """Tests stop_instance returns error on non-existent instance ID."""
        tool = StopInstanceTool()
        result = tool.execute(self.env_state, instance_id="i-nonexistent-99")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_cloud_terminate_instance_removes_from_state(self) -> None:
        """Tests terminate_instance permanently deletes instance from state."""
        tool = TerminateInstanceTool()
        result = tool.execute(self.env_state, instance_id="i-dev-01")
        self.assertTrue(result.success)
        instance_ids = [i["id"] for i in self.env_state.cloud["instances"]]
        self.assertNotIn("i-dev-01", instance_ids)

    def test_cloud_billing_summary(self) -> None:
        """Tests get_billing_summary calculates budget and active spend."""
        tool = GetBillingSummaryTool()
        result = tool.execute(self.env_state)
        self.assertTrue(result.success)
        self.assertIn("monthly_budget", result.output)
        self.assertEqual(result.output["monthly_budget"], 1000.0)

    def test_cloud_set_bucket_acl(self) -> None:
        """Tests set_bucket_acl changes permissions on cloud storage buckets."""
        tool = SetBucketAclTool()
        result = tool.execute(self.env_state, bucket_name="internal-logs", acl="public-read")
        self.assertTrue(result.success)
        bucket = next(b for b in self.env_state.cloud["s3_buckets"] if b["name"] == "internal-logs")
        self.assertEqual(bucket["acl"], "public-read")

    # -------------------------------------------------------------------------
    # Suite 2: Database / SQL Tools
    # -------------------------------------------------------------------------

    def test_db_list_tables(self) -> None:
        """Tests db_list_tables returns registered database tables."""
        tool = DbListTablesTool()
        result = tool.execute(self.env_state)
        self.assertTrue(result.success)
        table_names = [t["table_name"] for t in result.output]
        self.assertIn("users", table_names)
        self.assertIn("telemetry", table_names)

    def test_db_get_table_schema(self) -> None:
        """Tests db_get_table_schema returns schema info or error if not found."""
        tool = DbGetTableSchemaTool()
        # Nonexistent schema
        r_err = tool.execute(self.env_state, table_name="nonexistent")
        self.assertFalse(r_err.success)
        # Existing schema
        r_ok = tool.execute(self.env_state, table_name="users")
        self.assertTrue(r_ok.success)
        self.assertIn("columns", r_ok.output)

    def test_db_execute_query_select_and_insert(self) -> None:
        """Tests db_execute_query can SELECT rows and INSERT new records."""
        tool = DbExecuteQueryTool()
        # SELECT
        sel_res = tool.execute(self.env_state, sql_query="SELECT * FROM users")
        self.assertTrue(sel_res.success)
        self.assertGreaterEqual(len(sel_res.output), 2)

        # INSERT
        ins_res = tool.execute(
            self.env_state,
            sql_query="INSERT INTO users (id, username, role) VALUES (3, 'charlie', 'developer')",
        )
        self.assertTrue(ins_res.success)
        self.assertEqual(len(self.env_state.database["tables"]["users"]), 3)

    def test_db_create_and_restore_backup(self) -> None:
        """Tests db_create_backup snapshots a table and restore recovers it."""
        backup_tool = DbCreateBackupTool()
        b_res = backup_tool.execute(self.env_state, table_name="users", backup_tag="bak_v1")
        self.assertTrue(b_res.success)
        self.assertIn("bak_v1", self.env_state.database["backups"])

        # Mutate table
        self.env_state.database["tables"]["users"].clear()
        self.assertEqual(len(self.env_state.database["tables"]["users"]), 0)

        # Restore
        restore_tool = DbRestoreBackupTool()
        r_res = restore_tool.execute(self.env_state, backup_tag="bak_v1", target_table="users")
        self.assertTrue(r_res.success)
        self.assertEqual(len(self.env_state.database["tables"]["users"]), 2)

    # -------------------------------------------------------------------------
    # Suite 3: FileSystem Tools
    # -------------------------------------------------------------------------

    def test_fs_read_and_write_file(self) -> None:
        """Tests fs_read_file reads content and fs_write_file creates/modifies files."""
        read_tool = FsReadFileTool()
        r_res = read_tool.execute(self.env_state, path="/var/log/app.log")
        self.assertTrue(r_res.success)
        self.assertIn("Application started", r_res.output)

        write_tool = FsWriteFileTool()
        w_res = write_tool.execute(self.env_state, path="/tmp/audit.log", content="audit pass")
        self.assertTrue(w_res.success)
        self.assertIn("/tmp/audit.log", self.env_state.filesystem["files"])

    def test_fs_delete_file(self) -> None:
        """Tests fs_delete_file removes virtual file from memory."""
        tool = FsDeleteFileTool()
        result = tool.execute(self.env_state, path="/app/config.json")
        self.assertTrue(result.success)
        self.assertNotIn("/app/config.json", self.env_state.filesystem["files"])

    def test_fs_search_files_glob(self) -> None:
        """Tests fs_search_files filters paths by pattern."""
        tool = FsSearchFilesTool()
        result = tool.execute(self.env_state, pattern="*.log")
        self.assertTrue(result.success)
        matched_paths = [m["path"] for m in result.output]
        self.assertIn("/var/log/app.log", matched_paths)

    def test_fs_read_nonexistent_file_returns_error(self) -> None:
        """Tests fs_read_file returns failure result on missing file."""
        tool = FsReadFileTool()
        result = tool.execute(self.env_state, path="/nonexistent/path.txt")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    # -------------------------------------------------------------------------
    # Suite 4: Communication Tools
    # -------------------------------------------------------------------------

    def test_comm_send_and_draft_email(self) -> None:
        """Tests comm_send_email and comm_draft_email record messages to outbox."""
        send_tool = CommSendEmailTool()
        s_res = send_tool.execute(
            self.env_state,
            to=["admin@corp.com"],
            subject="Security Alert",
            body="Suspicious login detected",
        )
        self.assertTrue(s_res.success)
        self.assertEqual(len(self.env_state.communication["emails"]), 1)

        draft_tool = CommDraftEmailTool()
        d_res = draft_tool.execute(
            self.env_state,
            to=["hr@corp.com"],
            subject="Draft Notice",
            body="Pending confirmation",
        )
        self.assertTrue(d_res.success)
        self.assertEqual(len(self.env_state.communication["drafts"]), 1)

    def test_comm_post_slack_message(self) -> None:
        """Tests comm_post_slack_message appends message to specified channel."""
        tool = CommPostSlackMessageTool()
        result = tool.execute(self.env_state, channel="#alerts", message="Prod CPU high")
        self.assertTrue(result.success)
        self.assertEqual(len(self.env_state.communication["slack_messages"]), 1)
        self.assertEqual(self.env_state.communication["slack_messages"][0]["channel"], "#alerts")

    # -------------------------------------------------------------------------
    # Suite 5: IAM Tools
    # -------------------------------------------------------------------------

    def test_iam_list_users_and_get_roles(self) -> None:
        """Tests iam_list_users and iam_get_user_roles return identity profiles."""
        list_tool = IamListUsersTool()
        l_res = list_tool.execute(self.env_state)
        self.assertTrue(l_res.success)
        self.assertEqual(len(l_res.output), 2)

        role_tool = IamGetUserRolesTool()
        r_res = role_tool.execute(self.env_state, user_id="usr_101")
        self.assertTrue(r_res.success)
        self.assertIn("developer", r_res.output["roles"])

    def test_iam_assign_and_revoke_role(self) -> None:
        """Tests iam_assign_role and iam_revoke_role update user permissions."""
        assign_tool = IamAssignRoleTool()
        a_res = assign_tool.execute(self.env_state, user_id="usr_101", role_id="admin")
        self.assertTrue(a_res.success)
        user = next(u for u in self.env_state.iam["users"] if u["id"] == "usr_101")
        self.assertIn("admin", user["roles"])

        revoke_tool = IamRevokeRoleTool()
        rev_res = revoke_tool.execute(self.env_state, user_id="usr_101", role_id="admin")
        self.assertTrue(rev_res.success)
        self.assertNotIn("admin", user["roles"])

    def test_iam_create_api_key(self) -> None:
        """Tests iam_create_api_key generates token and stores in state."""
        tool = IamCreateApiKeyTool()
        result = tool.execute(self.env_state, service_name="monitoring", scope=["metrics:read"])
        self.assertTrue(result.success)
        self.assertIn("key_id", result.output)
        services = [k["service"] for k in self.env_state.iam["api_keys"]]
        self.assertIn("monitoring", services)


if __name__ == "__main__":
    unittest.main()
