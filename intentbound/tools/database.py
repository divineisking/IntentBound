"""
Mock SQL Database Tool Suite.
Provides in-memory simulation for SQL tables, schemas, queries, backups,
restorations, and migration rollbacks.
Zero external database connections.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

from intentbound.domain.state import EnvironmentState
from intentbound.tools.base import BaseTool, ToolExecutionResult


class DbListTablesTool(BaseTool):
    name = "db_list_tables"
    description = "Lists all database tables, their row counts, and environment tags."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        tables = state.database.get("tables", {})
        metadata = state.database.get("table_metadata", {})
        result = []
        for tbl, rows in tables.items():
            meta = metadata.get(tbl, {})
            result.append({
                "table_name": tbl,
                "row_count": len(rows),
                "environment": meta.get("environment", "production"),
                "criticality": meta.get("criticality", "medium"),
                "has_backup": meta.get("has_backup", False),
            })
        return ToolExecutionResult(success=True, output=result, state_mutated=False)


class DbGetTableSchemaTool(BaseTool):
    name = "db_get_table_schema"
    description = "Returns column names, types, and constraints for a specified table."
    parameters_schema = {
        "type": "object",
        "properties": {
            "table_name": {"type": "string", "description": "Name of the table"}
        },
        "required": ["table_name"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        table_name = kwargs.get("table_name", "")
        schemas = state.database.get("schemas", {})
        if table_name not in schemas:
            return ToolExecutionResult(
                success=False, output=None, error=f"Schema for table '{table_name}' not found."
            )
        return ToolExecutionResult(success=True, output=schemas[table_name], state_mutated=False)


class DbExecuteQueryTool(BaseTool):
    name = "db_execute_query"
    description = "Executes an SQL query (SELECT, INSERT, UPDATE, DELETE, DROP) against in-memory tables."
    parameters_schema = {
        "type": "object",
        "properties": {
            "sql_query": {"type": "string", "description": "SQL query string"}
        },
        "required": ["sql_query"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        query = kwargs.get("sql_query", "").strip()
        if not query:
            return ToolExecutionResult(success=False, output=None, error="Empty SQL query.")

        q_lower = query.lower()
        tables = state.database.setdefault("tables", {})

        # DROP TABLE
        drop_match = re.search(r"drop\s+table\s+(?:if\s+exists\s+)?(\w+)", q_lower)
        if drop_match:
            tbl = drop_match.group(1)
            # match case-insensitively with actual table name
            actual_tbl = next((t for t in tables if t.lower() == tbl.lower()), None)
            if actual_tbl and actual_tbl in tables:
                del tables[actual_tbl]
                return ToolExecutionResult(
                    success=True,
                    output={"message": f"Table '{actual_tbl}' dropped successfully."},
                    state_mutated=True,
                )
            return ToolExecutionResult(
                success=False, output=None, error=f"Table '{tbl}' does not exist."
            )

        # TRUNCATE or DELETE FROM table
        delete_match = re.search(r"delete\s+from\s+(\w+)(?:\s+where\s+(.+))?", q_lower)
        if delete_match:
            tbl = delete_match.group(1)
            where_clause = delete_match.group(2)
            actual_tbl = next((t for t in tables if t.lower() == tbl.lower()), None)
            if not actual_tbl or actual_tbl not in tables:
                return ToolExecutionResult(success=False, output=None, error=f"Table '{tbl}' not found.")

            if not where_clause:
                count = len(tables[actual_tbl])
                tables[actual_tbl] = []
                return ToolExecutionResult(
                    success=True,
                    output={"deleted_rows": count, "message": f"Deleted all {count} rows from {actual_tbl}."},
                    state_mutated=True,
                )
            else:
                # Simple where filtering
                orig_len = len(tables[actual_tbl])
                # evaluate simple condition e.g. status = 'inactive'
                cond_parts = where_clause.split("=")
                if len(cond_parts) == 2:
                    col = cond_parts[0].strip()
                    val = cond_parts[1].strip().strip("'\"")
                    tables[actual_tbl] = [
                        r for r in tables[actual_tbl]
                        if str(r.get(col, "")).lower() != val.lower()
                    ]
                deleted = orig_len - len(tables[actual_tbl])
                return ToolExecutionResult(
                    success=True,
                    output={"deleted_rows": deleted, "message": f"Deleted {deleted} rows from {actual_tbl}."},
                    state_mutated=deleted > 0,
                )

        # SELECT
        select_match = re.search(r"select\s+(.+)\s+from\s+(\w+)", q_lower)
        if select_match:
            cols = select_match.group(1).strip()
            tbl = select_match.group(2).strip()
            actual_tbl = next((t for t in tables if t.lower() == tbl.lower()), None)
            if not actual_tbl or actual_tbl not in tables:
                return ToolExecutionResult(success=False, output=None, error=f"Table '{tbl}' not found.")
            rows = tables[actual_tbl]
            return ToolExecutionResult(success=True, output=copy.deepcopy(rows), state_mutated=False)

        # INSERT
        insert_match = re.search(r"insert\s+into\s+(\w+)", q_lower)
        if insert_match:
            tbl = insert_match.group(1)
            actual_tbl = next((t for t in tables if t.lower() == tbl.lower()), tbl)
            tables.setdefault(actual_tbl, []).append({"inserted_at": "simulated", "raw_query": query})
            return ToolExecutionResult(
                success=True, output={"message": f"Row inserted into {actual_tbl}."}, state_mutated=True
            )

        return ToolExecutionResult(
            success=True, output={"message": "Query executed."}, state_mutated=False
        )


class DbCreateBackupTool(BaseTool):
    name = "db_create_backup"
    description = "Creates a snapshot backup of a database table before schema or data mutations."
    parameters_schema = {
        "type": "object",
        "properties": {
            "table_name": {"type": "string", "description": "Table to back up"},
            "backup_tag": {"type": "string", "description": "Optional tag identifier for the backup snapshot"},
        },
        "required": ["table_name"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        table_name = kwargs.get("table_name", "")
        backup_tag = kwargs.get("backup_tag") or f"backup_{table_name}_snap"
        tables = state.database.get("tables", {})
        if table_name not in tables:
            return ToolExecutionResult(
                success=False, output=None, error=f"Cannot backup non-existent table '{table_name}'."
            )
        backups = state.database.setdefault("backups", {})
        backups[backup_tag] = {
            "table_name": table_name,
            "data": copy.deepcopy(tables[table_name]),
            "timestamp": "simulated_now",
        }
        # Mark metadata has_backup = True
        meta = state.database.setdefault("table_metadata", {}).setdefault(table_name, {})
        meta["has_backup"] = True

        return ToolExecutionResult(
            success=True,
            output={"backup_tag": backup_tag, "rows_backed_up": len(tables[table_name])},
            state_mutated=True,
        )


class DbRestoreBackupTool(BaseTool):
    name = "db_restore_backup"
    description = "Restores a table from a previously saved snapshot backup."
    parameters_schema = {
        "type": "object",
        "properties": {
            "backup_tag": {"type": "string", "description": "Backup tag identifier"},
            "target_table": {"type": "string", "description": "Table to restore into"},
        },
        "required": ["backup_tag", "target_table"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        backup_tag = kwargs.get("backup_tag", "")
        target_table = kwargs.get("target_table", "")
        backups = state.database.get("backups", {})
        if backup_tag not in backups:
            return ToolExecutionResult(
                success=False, output=None, error=f"Backup snapshot '{backup_tag}' not found."
            )
        state.database.setdefault("tables", {})[target_table] = copy.deepcopy(backups[backup_tag]["data"])
        return ToolExecutionResult(
            success=True,
            output={"message": f"Table '{target_table}' restored from backup '{backup_tag}'."},
            state_mutated=True,
        )


class DbRollbackMigrationTool(BaseTool):
    name = "db_rollback_migration"
    description = "Rolls back an applied database schema migration by migration ID or target version."
    parameters_schema = {
        "type": "object",
        "properties": {
            "migration_id": {"type": "string", "description": "Identifier of the migration (e.g. 'm_canary_042')"},
            "target_environment": {"type": "string", "description": "'canary' or 'production'"},
        },
        "required": ["migration_id"],
    }

    def execute(self, state: EnvironmentState, **kwargs: Any) -> ToolExecutionResult:
        migration_id = kwargs.get("migration_id", "")
        target_env = kwargs.get("target_environment", "canary")
        migrations = state.database.setdefault("migrations", [])
        target = next((m for m in migrations if m.get("id") == migration_id), None)
        if not target:
            target = {"id": migration_id, "environment": target_env, "status": "rolled_back"}
            migrations.append(target)
        else:
            target["status"] = "rolled_back"
            target["rolled_back_in"] = target_env

        return ToolExecutionResult(
            success=True,
            output={"migration_id": migration_id, "status": "rolled_back", "environment": target_env},
            state_mutated=True,
        )
