"""
IntentBound Simulated Tools Suite.
Zero external network, disk, or cloud API dependencies.
"""

import copy

from intentbound.tools.base import (
    BaseTool,
    ToolExecutionResult,
    ToolRegistry,
    ActionLogger,
)
from intentbound.tools.cloud import (
    ListInstancesTool,
    GetInstanceMetricsTool,
    StopInstanceTool,
    TerminateInstanceTool,
    ResizeInstanceTool,
    GetBillingSummaryTool,
    ListS3BucketsTool,
    SetBucketAclTool,
    CreateChangeTicketTool,
    UpdateSecurityGroupRuleTool,
)
from intentbound.tools.database import (
    DbListTablesTool,
    DbGetTableSchemaTool,
    DbExecuteQueryTool,
    DbCreateBackupTool,
    DbRestoreBackupTool,
    DbRollbackMigrationTool,
)
from intentbound.tools.filesystem import (
    FsListDirectoryTool,
    FsReadFileTool,
    FsWriteFileTool,
    FsDeleteFileTool,
    FsSearchFilesTool,
    FsChmodTool,
    FsQuarantineFileTool,
)
from intentbound.tools.communication import (
    CommSendEmailTool,
    CommDraftEmailTool,
    CommPostSlackMessageTool,
    CommListChannelsTool,
    CommCreateSupportTicketTool,
    CommCloseSupportTicketTool,
    CommExportToWebhookTool,
)
from intentbound.tools.iam import (
    IamListUsersTool,
    IamGetUserRolesTool,
    IamAssignRoleTool,
    IamRevokeRoleTool,
    IamCreateApiKeyTool,
    IamDeactivateUserTool,
    IamModifyMfaTool,
    IamGetAuditLogTool,
)
from intentbound.tools.admin import (
    AskClarificationTool,
    CheckDiskUsageTool,
    CheckSyncStatusTool,
    DeleteDirectoryTool,
    CompressDirectoryTool,
    GetResourcePolicyTool,
    GrantDirectAccessTool,
    SubmitAccessRequestTool,
    NotifyUserTool,
    ListServicesTool,
    GetMigrationHistoryTool,
    RollbackMigrationTool,
    SearchEmployeeTool,
    GetEmployeeDetailsTool,
    DeprovisionUserAccountTool,
    UpdateDeploymentTool,
    ValidateDeploymentSpecTool,
    ListBranchesTool,
    GetBranchDiffTool,
    DeleteRemoteBranchTool,
    GetUserSecurityProfileTool,
    SetStaticPasswordTool,
    DisableUserMfaTool,
    SendOutOfBandRecoveryLinkTool,
    FlagSuspiciousTicketTool,
)
from intentbound.tools.secops import (
    GetFirewallRulesTool,
    GetDroppedPacketLogsTool,
    AddFirewallRuleTool,
    DisableFirewallTool,
    SetDefaultPolicyTool,
    CreateTarballTool,
    SanitizeSecretsTool,
    HttpPostTool,
    ReportSecurityConcernTool,
    VerifyAssetOwnershipTool,
    RunPortScanTool,
    GenerateComplianceReportTool,
    CalculateFileHashTool,
    ReadFileHeaderTool,
    ShredFileTool,
    LogThreatIndicatorTool,
)


def create_default_tool_registry() -> ToolRegistry:
    """Instantiates and populates a ToolRegistry with all standard simulated tools."""
    registry = ToolRegistry()

    # Cloud Tools
    registry.register(ListInstancesTool())
    registry.register(GetInstanceMetricsTool())
    registry.register(StopInstanceTool())
    registry.register(TerminateInstanceTool())
    registry.register(ResizeInstanceTool())
    registry.register(GetBillingSummaryTool())
    registry.register(ListS3BucketsTool())
    registry.register(SetBucketAclTool())
    registry.register(CreateChangeTicketTool())
    registry.register(UpdateSecurityGroupRuleTool())

    # Database Tools
    registry.register(DbListTablesTool())
    registry.register(DbGetTableSchemaTool())
    registry.register(DbExecuteQueryTool())
    registry.register(DbCreateBackupTool())
    registry.register(DbRestoreBackupTool())
    registry.register(DbRollbackMigrationTool())

    # Filesystem Tools
    registry.register(FsListDirectoryTool())
    registry.register(FsReadFileTool())
    registry.register(FsWriteFileTool())
    registry.register(FsDeleteFileTool())
    registry.register(FsSearchFilesTool())
    registry.register(FsChmodTool())
    registry.register(FsQuarantineFileTool())

    # Communication Tools
    registry.register(CommSendEmailTool())
    registry.register(CommDraftEmailTool())
    registry.register(CommPostSlackMessageTool())
    registry.register(CommListChannelsTool())
    registry.register(CommCreateSupportTicketTool())
    registry.register(CommCloseSupportTicketTool())
    registry.register(CommExportToWebhookTool())

    # IAM Tools
    registry.register(IamListUsersTool())
    registry.register(IamGetUserRolesTool())
    registry.register(IamAssignRoleTool())
    registry.register(IamRevokeRoleTool())
    registry.register(IamCreateApiKeyTool())
    registry.register(IamDeactivateUserTool())
    registry.register(IamModifyMfaTool())
    registry.register(IamGetAuditLogTool())

    # Admin & DevOps Tools
    registry.register(AskClarificationTool())
    registry.register(CheckDiskUsageTool())
    registry.register(CheckSyncStatusTool())
    registry.register(DeleteDirectoryTool())
    registry.register(CompressDirectoryTool())
    registry.register(GetResourcePolicyTool())
    registry.register(GrantDirectAccessTool())
    registry.register(SubmitAccessRequestTool())
    registry.register(NotifyUserTool())
    registry.register(ListServicesTool())
    registry.register(GetMigrationHistoryTool())
    registry.register(RollbackMigrationTool())
    registry.register(SearchEmployeeTool())
    registry.register(GetEmployeeDetailsTool())
    registry.register(DeprovisionUserAccountTool())
    registry.register(UpdateDeploymentTool())
    registry.register(ValidateDeploymentSpecTool())
    registry.register(ListBranchesTool())
    registry.register(GetBranchDiffTool())
    registry.register(DeleteRemoteBranchTool())
    registry.register(GetUserSecurityProfileTool())
    registry.register(SetStaticPasswordTool())
    registry.register(DisableUserMfaTool())
    registry.register(SendOutOfBandRecoveryLinkTool())
    registry.register(FlagSuspiciousTicketTool())

    # SecOps Tools
    registry.register(GetFirewallRulesTool())
    registry.register(GetDroppedPacketLogsTool())
    registry.register(AddFirewallRuleTool())
    registry.register(DisableFirewallTool())
    registry.register(SetDefaultPolicyTool())
    registry.register(CreateTarballTool())
    registry.register(SanitizeSecretsTool())
    registry.register(HttpPostTool())
    registry.register(ReportSecurityConcernTool())
    registry.register(VerifyAssetOwnershipTool())
    registry.register(RunPortScanTool())
    registry.register(GenerateComplianceReportTool())
    registry.register(CalculateFileHashTool())
    registry.register(ReadFileHeaderTool())
    registry.register(ShredFileTool())
    registry.register(LogThreatIndicatorTool())

    # Convenience aliases matching scenario naming
    alias_map = {
        "read_file": FsReadFileTool(),
        "write_file": FsWriteFileTool(),
        "list_directory": FsListDirectoryTool(),
        "get_user_roles": IamGetUserRolesTool(),
    }
    for alias_name, alias_tool in alias_map.items():
        # register under alias
        aliased = copy.deepcopy(alias_tool)
        aliased.name = alias_name
        registry.register(aliased)

    return registry


__all__ = [
    "BaseTool",
    "ToolExecutionResult",
    "ToolRegistry",
    "ActionLogger",
    "create_default_tool_registry",
]
