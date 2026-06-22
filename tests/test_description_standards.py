"""
Tests verifying OpenAPI spec descriptions conform to ADR 0003 (description standards).

ADR 0003 rules encoded here:
  §2  Write descriptions only when they add value beyond field name + type.
      A missing description is intentional (self-evident). A tautological
      description ('Integration ID.', 'Job type.') is worse than nothing.
  §3  Enum field descriptions must explain what values *do*, not just list them.

These tests are table-driven. To sweep the next spec, add rows to the tables
below — no new test functions needed.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _load(api_dir: str) -> dict:
    spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
    if not spec_path.exists():
        pytest.skip(f"{api_dir} spec not found")
    return json.loads(spec_path.read_text(encoding="utf-8"))


def _navigate(spec: dict, path: list[str]):
    """Navigate a nested dict by a list of string keys. Returns None if any key is missing."""
    current = spec
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


# ─── Schemas that must have a schema-level description ────────────────────────
#
# Include a shared schema here when its name alone is insufficient for a
# consumer to understand its purpose or shape. CRUD object names ('Workspace',
# 'User') are often self-evident; envelope/metadata schemas ('Status',
# 'PagingMeta', 'RunRecord') are not.
#
# path: list of dict keys leading to the schema object in the spec.
# Add rows for additional specs as they are swept against ADR 0003.

_SCHEMA_MUST_HAVE_DESCRIPTION = [
    # CloudWorks — envelope and metadata schemas (names alone are ambiguous)
    pytest.param("cloudworks", ["components", "schemas", "Status"],            id="cw-status"),
    pytest.param("cloudworks", ["components", "schemas", "ErrorStatus"],        id="cw-errorstatus"),
    pytest.param("cloudworks", ["components", "schemas", "PagingMeta"],         id="cw-pagingmeta"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary"], id="cw-integrationsummary"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationDetail"],  id="cw-integrationdetail"),
    pytest.param("cloudworks", ["components", "schemas", "RunRecord"],          id="cw-runrecord"),
    pytest.param("cloudworks", ["components", "schemas", "NotificationConfig"], id="cw-notificationconfig"),
    # ALM — envelope and metadata schemas (names alone are ambiguous)
    pytest.param("alm", ["components", "schemas", "Meta"],       id="alm-meta"),
    pytest.param("alm", ["components", "schemas", "Status"],     id="alm-status"),
    pytest.param("alm", ["components", "schemas", "TaskResult"], id="alm-taskresult"),
    pytest.param("alm", ["components", "schemas", "TaskError"],  id="alm-taskerror"),
    # Audit — envelope and metadata schemas (names alone are ambiguous or name an abstract concept)
    pytest.param("audit", ["components", "schemas", "AuditPaging"],        id="audit-auditpaging"),
    pytest.param("audit", ["components", "schemas", "AuditEventsResponse"], id="audit-auditeventsresponse"),
    pytest.param("audit", ["components", "schemas", "AuditErrorResponse"],  id="audit-auditerrorresponse"),
    pytest.param("audit", ["components", "schemas", "AuditSearchRequest"],  id="audit-auditsearchrequest"),
    # Authentication — envelope and request-body schemas whose names alone are ambiguous
    pytest.param("authentication", ["components", "schemas", "CertPayload"],   id="auth-certpayload"),
    pytest.param("authentication", ["components", "schemas", "ValidationUrl"], id="auth-validationurl"),
    # Financial Consolidation — non-obvious schemas (names insufficient without description)
    pytest.param("financial-consolidation", ["components", "schemas", "WorkflowStateResponse"],   id="fc-workflowstateresponse"),
    pytest.param("financial-consolidation", ["components", "schemas", "ODataRecord"],             id="fc-odatarecord"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMembersResponse"], id="fc-dimensionmembersresponse"),
    # SCIM — envelope and protocol schemas whose names alone are insufficient for a consumer
    pytest.param("scim", ["components", "schemas", "ListResponse"], id="scim-listresponse"),
    pytest.param("scim", ["components", "schemas", "ScimError"],    id="scim-scimerror"),
    pytest.param("scim", ["components", "schemas", "PatchOp"],      id="scim-patchop"),
    # Exception — ExceptionUserSearchRequest: oneOf semantics and exactly-one constraint not conveyed by name alone
    pytest.param("exception", ["components", "schemas", "ExceptionUserSearchRequest"], id="exc-exceptionusersearchrequest"),
    # Integration — status and metadata envelopes whose names alone are insufficient
    pytest.param("integration", ["components", "schemas", "Status"],          id="int-status"),
    pytest.param("integration", ["components", "schemas", "Meta"],            id="int-meta"),
    pytest.param("integration", ["components", "schemas", "ViewReadRequest"], id="int-viewreadrequest"),
]


@pytest.mark.parametrize("api_dir,path", _SCHEMA_MUST_HAVE_DESCRIPTION)
def test_schema_has_description(api_dir, path):
    """Shared schemas whose names are not self-evident must have a schema-level description (ADR 0003 §2)."""
    spec = _load(api_dir)
    obj = _navigate(spec, path)
    assert obj is not None, f"{api_dir}: schema not found at {'.'.join(path)}"
    assert obj.get("description", "").strip(), (
        f"{api_dir}: {'.'.join(path)} must have a non-empty 'description' — "
        f"the schema name alone is insufficient for a consumer to understand "
        f"the object's purpose (ADR 0003 §2)"
    )


# ─── Properties that must have a description ──────────────────────────────────
#
# Include a property here when its name and type are insufficient to understand
# it. Fields whose meaning is clear from name + type (e.g. 'createdBy: string',
# 'startDate: string, format: date-time') are intentionally omitted.
#
# path: list of dict keys leading to the property object in the spec.

_PROPERTY_MUST_HAVE_DESCRIPTION = [
    # CloudWorks — IntegrationSummary
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "latestRun"],                                   id="cw-latestrun"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "latestRun", "properties", "triggeredBy"],       id="cw-latestrun-triggeredby"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "latestRun", "properties", "message"],           id="cw-latestrun-message"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "latestRun", "properties", "executionErrorCode"], id="cw-latestrun-errorcode"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "nuxVisible"],                                   id="cw-nuxvisible"),
    pytest.param("cloudworks", ["components", "schemas", "IntegrationSummary", "properties", "notificationId"],                               id="cw-notificationid"),
    # CloudWorks — RunRecord (same ambiguous fields, different schema)
    pytest.param("cloudworks", ["components", "schemas", "RunRecord", "properties", "triggeredBy"],      id="cw-runrecord-triggeredby"),
    pytest.param("cloudworks", ["components", "schemas", "RunRecord", "properties", "message"],          id="cw-runrecord-message"),
    pytest.param("cloudworks", ["components", "schemas", "RunRecord", "properties", "executionErrorCode"], id="cw-runrecord-errorcode"),
    # CloudWorks — PagingMeta.schema (a URL field, not a JSON Schema object)
    pytest.param("cloudworks", ["components", "schemas", "PagingMeta", "properties", "schema"],         id="cw-pagingmeta-schema-field"),
    # CloudWorks — ErrorStatus nested message
    pytest.param("cloudworks", ["components", "schemas", "ErrorStatus", "properties", "status", "properties", "message"], id="cw-errorstatus-nested-message"),
    # CloudWorks — NotificationRequest.notifications (generic name; shape not obvious)
    pytest.param("cloudworks", ["components", "schemas", "NotificationRequest", "properties", "notifications"], id="cw-notificationrequest-notifications"),
    # ALM — Status properties (code could be confused with HTTP status; message is ambiguous)
    pytest.param("alm", ["components", "schemas", "Status", "properties", "code"],    id="alm-status-code"),
    pytest.param("alm", ["components", "schemas", "Status", "properties", "message"], id="alm-status-message"),
    # ALM — TaskError properties (title vs messageText distinction not obvious from names alone)
    pytest.param("alm", ["components", "schemas", "TaskError", "properties", "title"],       id="alm-taskerror-title"),
    pytest.param("alm", ["components", "schemas", "TaskError", "properties", "messageText"], id="alm-taskerror-messagetext"),
    # Audit — AuditEvent properties where name + type are insufficient
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "id"],                    id="audit-auditevent-id"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "eventTypeId"],           id="audit-auditevent-eventtypeid"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "message"],               id="audit-auditevent-message"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "errorNumber"],           id="audit-auditevent-errornumber"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "additionalAttributes"],  id="audit-auditevent-additionalattributes"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "eventDate"],             id="audit-auditevent-eventdate"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "createdDate"],           id="audit-auditevent-createddate"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "checksum"],              id="audit-auditevent-checksum"),
    # Audit — AuditPaging properties where conditionality or zero-based indexing is non-obvious
    pytest.param("audit", ["components", "schemas", "AuditPaging", "properties", "offSet"],        id="audit-paging-offset"),
    pytest.param("audit", ["components", "schemas", "AuditPaging", "properties", "nextOffset"],    id="audit-paging-nextoffset"),
    pytest.param("audit", ["components", "schemas", "AuditPaging", "properties", "previousUrl"],   id="audit-paging-previousurl"),
    # Authentication — CertPayload.signature needs algorithm+encoding context; tokenValue must name the correct header format
    pytest.param("authentication", ["components", "schemas", "CertPayload", "properties", "signature"],  id="auth-certpayload-signature"),
    pytest.param("authentication", ["components", "schemas", "TokenInfo", "properties", "tokenValue"],   id="auth-tokeninfo-tokenvalue"),
    # Financial Consolidation — WorkflowStateResponse.runId: null UUID meaning is non-obvious from name alone
    pytest.param("financial-consolidation", ["components", "schemas", "WorkflowStateResponse", "properties", "runId"],                id="fc-workflowstateresponse-runid"),
    # Financial Consolidation — DimensionProperty: type examples and built-in flag meaning are non-obvious
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "propertyType"],            id="fc-dimensionproperty-propertytype"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "standardProperty"],        id="fc-dimensionproperty-standardproperty"),
    # Financial Consolidation — Dimension: translations field needs language-code context
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "translations"],                    id="fc-dimension-translations"),
    # Financial Consolidation — DimensionMember: non-obvious fields (path, leaf semantics, effective dates, property bag)
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "ancestors"],                 id="fc-dimensionmember-ancestors"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "isLeaf"],                    id="fc-dimensionmember-isleaf"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "startDate"],                 id="fc-dimensionmember-startdate"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "endDate"],                   id="fc-dimensionmember-enddate"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "properties"],                id="fc-dimensionmember-properties"),
    # Financial Consolidation — User: userId is internal, userName is not the email, isDisabled has inverted-boolean semantics, email is distinct from userName
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "userId"],                              id="fc-user-userid"),
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "userName"],                             id="fc-user-username"),
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "isDisabled"],                           id="fc-user-isdisabled"),
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "email"],                                id="fc-user-email"),
    # Financial Consolidation — UserInput: userName context needed to distinguish from email address
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput", "properties", "userName"],                        id="fc-userinput-username"),
    # OAuth — TokenResponse: non-obvious fields whose name + type are insufficient
    pytest.param("oauth", ["components", "schemas", "TokenResponse", "properties", "access_token"],  id="oauth-tokenresponse-access_token"),
    pytest.param("oauth", ["components", "schemas", "TokenResponse", "properties", "refresh_token"], id="oauth-tokenresponse-refresh_token"),
    pytest.param("oauth", ["components", "schemas", "TokenResponse", "properties", "scope"],         id="oauth-tokenresponse-scope"),
    pytest.param("oauth", ["components", "schemas", "TokenResponse", "properties", "expires_in"],    id="oauth-tokenresponse-expires_in"),
    # OAuth — ErrorPayload.error: device grant polling codes are not obvious from the enum alone
    pytest.param("oauth", ["components", "schemas", "ErrorPayload", "properties", "error"],          id="oauth-errorpayload-error"),
    # OAuth — RefreshPayload.client_secret: required vs omit distinction by grant type is non-obvious
    pytest.param("oauth", ["components", "schemas", "RefreshPayload", "properties", "client_secret"], id="oauth-refreshpayload-client_secret"),
    # OAuth — AuthCodePayload.code: the source of this code (redirect callback) is non-obvious
    pytest.param("oauth", ["components", "schemas", "AuthCodePayload", "properties", "code"],         id="oauth-authcodepayload-code"),
    # SCIM — schemas fields are SCIM protocol fields (URN arrays); their purpose is not self-evident from name alone
    pytest.param("scim", ["components", "schemas", "User", "properties", "schemas"],         id="scim-user-schemas"),
    pytest.param("scim", ["components", "schemas", "ListResponse", "properties", "schemas"], id="scim-listresponse-schemas"),
    pytest.param("scim", ["components", "schemas", "ScimError", "properties", "schemas"],    id="scim-scimerror-schemas"),
    pytest.param("scim", ["components", "schemas", "PatchOp", "properties", "schemas"],      id="scim-patchop-schemas"),
    # Exception — ExceptionUserPatchRequest.op: enum behavior (grant/revoke) non-obvious from values alone (ADR 0003 §3)
    pytest.param("exception", ["components", "schemas", "ExceptionUserPatchRequest", "properties", "op"],             id="exc-patchrequest-op"),
    # Exception — ExceptionUserPatchRequest.workspaceGuid: SSO-enabled constraint not derivable from name + type
    pytest.param("exception", ["components", "schemas", "ExceptionUserPatchRequest", "properties", "workspaceGuid"],  id="exc-patchrequest-workspaceguid"),
    # Exception — ExceptionUserSearchByWorkspaceRequest.workspaceGuid: "including visitors" behavior is non-obvious
    pytest.param("exception", ["components", "schemas", "ExceptionUserSearchByWorkspaceRequest", "properties", "workspaceGuid"], id="exc-searchbyworkspace-workspaceguid"),
    # Exception — ExceptionUserSearchByUserRequest.userGuid: visitor-exclusion behavior is non-obvious from name alone
    pytest.param("exception", ["components", "schemas", "ExceptionUserSearchByUserRequest", "properties", "userGuid"],           id="exc-searchbyuser-userguid"),
    # Exception — ErrorResponse.status: machine-readable error code (FAILURE_BAD_HEADER etc.) not obvious from name
    pytest.param("exception", ["components", "schemas", "ErrorResponse", "properties", "status"],        id="exc-errorresponse-status"),
    # Exception — ErrorResponse.statusMessage: distinguishes human-readable text from the machine-readable status code
    pytest.param("exception", ["components", "schemas", "ErrorResponse", "properties", "statusMessage"], id="exc-errorresponse-statusmessage"),
    # Integration — ModelCalendar: calendar type and 4-4-5 week placement non-obvious
    pytest.param("integration", ["components", "schemas", "ModelCalendar", "properties", "calendarType"],   id="int-modelcalendar-calendartype"),
    pytest.param("integration", ["components", "schemas", "ModelCalendar", "properties", "extraWeekMonth"], id="int-modelcalendar-extraweekmonth"),
    # Integration — Version: actual/forecast boolean flags non-obvious from name alone
    pytest.param("integration", ["components", "schemas", "Version", "properties", "isActual"],  id="int-version-isactual"),
    pytest.param("integration", ["components", "schemas", "Version", "properties", "isCurrent"], id="int-version-iscurrent"),
    # Integration — File: row-index semantics and origin type require context
    pytest.param("integration", ["components", "schemas", "File", "properties", "firstDataRow"], id="int-file-firstdatarow"),
    pytest.param("integration", ["components", "schemas", "File", "properties", "headerRow"],    id="int-file-headerrow"),
    pytest.param("integration", ["components", "schemas", "File", "properties", "origin"],       id="int-file-origin"),
    # Integration — Task.result: conditional presence (absent until terminal state) non-obvious
    pytest.param("integration", ["components", "schemas", "Task", "properties", "result"], id="int-task-result"),
    # Integration — TaskResult: failure dump availability and which object was processed
    pytest.param("integration", ["components", "schemas", "TaskResult", "properties", "failureDumpAvailable"], id="int-taskresult-failuredumpavailable"),
    pytest.param("integration", ["components", "schemas", "TaskResult", "properties", "objectId"],             id="int-taskresult-objectid"),
    pytest.param("integration", ["components", "schemas", "TaskResult", "properties", "objectName"],           id="int-taskresult-objectname"),
    # Integration — Meta.schema: a URL field, not a JSON Schema object
    pytest.param("integration", ["components", "schemas", "Meta", "properties", "schema"], id="int-meta-schema"),
    # Integration — Status: code is Anaplan-specific (not HTTP); message is the human-readable outcome
    pytest.param("integration", ["components", "schemas", "Status", "properties", "code"],    id="int-status-code"),
    pytest.param("integration", ["components", "schemas", "Status", "properties", "message"], id="int-status-message"),
    # Integration — numeric IDs: 12-digit type-prefixed strings; format is non-obvious from name + type alone
    pytest.param("integration", ["components", "schemas", "Import",    "properties", "id"], id="int-import-id"),
    pytest.param("integration", ["components", "schemas", "Export",    "properties", "id"], id="int-export-id"),
    pytest.param("integration", ["components", "schemas", "Process",   "properties", "id"], id="int-process-id"),
    pytest.param("integration", ["components", "schemas", "File",      "properties", "id"], id="int-file-id"),
    pytest.param("integration", ["components", "schemas", "List",      "properties", "id"], id="int-list-id"),
    pytest.param("integration", ["components", "schemas", "Module",    "properties", "id"], id="int-module-id"),
    pytest.param("integration", ["components", "schemas", "View",      "properties", "id"], id="int-view-id"),
    # Integration — File: encoding observed values (ISO-8859-1, UTF-16LE, UTF-8) non-obvious
    pytest.param("integration", ["components", "schemas", "File", "properties", "encoding"], id="int-file-encoding"),
    # Integration — CurrentPeriod.periodText: human-readable label, empty string when unset
    pytest.param("integration", ["components", "schemas", "CurrentPeriod", "properties", "periodText"], id="int-currentperiod-periodtext"),
    # Integration — Import.importType: confirmed enum values non-obvious
    pytest.param("integration", ["components", "schemas", "Import", "properties", "importType"], id="int-import-importtype"),
    # Integration — Export.exportType: confirmed enum values non-obvious
    pytest.param("integration", ["components", "schemas", "Export", "properties", "exportType"], id="int-export-exporttype"),
    # Integration — ImportMetadata.type: distinguishes source type (FILE/MODEL) from import content type
    pytest.param("integration", ["components", "schemas", "ImportMetadata", "properties", "type"], id="int-importmetadata-type"),
]


@pytest.mark.parametrize("api_dir,path", _PROPERTY_MUST_HAVE_DESCRIPTION)
def test_property_has_description(api_dir, path):
    """Specific ambiguous properties must carry descriptions (ADR 0003 §2)."""
    spec = _load(api_dir)
    obj = _navigate(spec, path)
    assert obj is not None, (
        f"{api_dir}: property not found at {'.'.join(path)}"
    )
    assert obj.get("description", "").strip(), (
        f"{api_dir}: {'.'.join(path)} must have a non-empty 'description' — "
        f"the field name alone is insufficient for a consumer to understand "
        f"its purpose (ADR 0003 §2)"
    )


# ─── Descriptions that must be absent ────────────────────────────────────────
#
# Include an object here when it is self-evident from name + type OR when its
# enum is self-documenting and the description would only restate it.
#
# Tautological descriptions ('Integration ID.', 'Job type.') are actively
# harmful: they train readers to ignore descriptions. Absent is correct.
# (ADR 0003 §2 and §3)
#
# path: list of dict keys leading to the object whose 'description' must be absent.

_MUST_NOT_HAVE_DESCRIPTION = [
    # CloudWorks Job.type — 'Job type.' adds nothing; enum values are self-explanatory
    pytest.param("cloudworks", ["components", "schemas", "Job", "properties", "type"],        id="cw-job-type"),
    # CloudWorks Schedule — 'Schedule name.' and 'Schedule type.' are tautological
    pytest.param("cloudworks", ["components", "schemas", "Schedule", "properties", "name"],   id="cw-schedule-name"),
    pytest.param("cloudworks", ["components", "schemas", "Schedule", "properties", "type"],   id="cw-schedule-type"),
    # ALM Revision — all field descriptions restate the name; name + type already say it all
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "id"],          id="alm-revision-id"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "name"],        id="alm-revision-name"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "description"], id="alm-revision-description"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "createdOn"],   id="alm-revision-createdon"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "createdBy"],   id="alm-revision-createdby"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "appliedOn"],   id="alm-revision-appliedon"),
    pytest.param("alm", ["components", "schemas", "Revision", "properties", "appliedBy"],   id="alm-revision-appliedby"),
    # ALM SyncTask — taskId is self-evident; taskState enum is self-explanatory; creationTime has format
    pytest.param("alm", ["components", "schemas", "SyncTask", "properties", "taskId"],       id="alm-synctask-taskid"),
    pytest.param("alm", ["components", "schemas", "SyncTask", "properties", "taskState"],    id="alm-synctask-taskstate"),
    pytest.param("alm", ["components", "schemas", "SyncTask", "properties", "creationTime"], id="alm-synctask-creationtime"),
    # ALM TaskResult — 'Whether the task completed successfully.' restates the boolean field name
    pytest.param("alm", ["components", "schemas", "TaskResult", "properties", "successful"], id="alm-taskresult-successful"),
    # ALM SyncTaskRequest — 'ID of the source model.' adds nothing over the field name
    pytest.param("alm", ["components", "schemas", "SyncTaskRequest", "properties", "sourceModelId"], id="alm-synctaskrequest-sourcemodelid"),
    # ALM OnlineStatusRequest.status — enum [online, offline] is self-explanatory
    pytest.param("alm", ["components", "schemas", "OnlineStatusRequest", "properties", "status"], id="alm-onlinestatus-status"),
    # ALM AppliedModel.modelDeleted — boolean field name is self-evident
    pytest.param("alm", ["components", "schemas", "AppliedModel", "properties", "modelDeleted"], id="alm-appliedmodel-modeldeleted"),
    # Audit AuditEvent (schema) — 'A single audit event record.' restates the name
    pytest.param("audit", ["components", "schemas", "AuditEvent"],                                                id="audit-auditevent-schema"),
    # Audit AuditEvent properties — field name and type already express the meaning
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "userId"],        id="audit-auditevent-userid"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "tenantId"],      id="audit-auditevent-tenantid"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "success"],       id="audit-auditevent-success"),
    pytest.param("audit", ["components", "schemas", "AuditEvent", "properties", "userAgent"],     id="audit-auditevent-useragent"),
    # Audit AuditPaging properties — field names are self-evident in a pagination context
    pytest.param("audit", ["components", "schemas", "AuditPaging", "properties", "currentPageSize"], id="audit-paging-currentpagesize"),
    pytest.param("audit", ["components", "schemas", "AuditPaging", "properties", "nextUrl"],         id="audit-paging-nexturl"),
    # Authentication TokenInfo — uuid fields are self-evident from name + format; ErrorResponse.status enum values are self-documenting
    pytest.param("authentication", ["components", "schemas", "TokenInfo", "properties", "tokenId"],        id="auth-tokeninfo-tokenid"),
    pytest.param("authentication", ["components", "schemas", "TokenInfo", "properties", "refreshTokenId"], id="auth-tokeninfo-refreshtokenid"),
    pytest.param("authentication", ["components", "schemas", "ErrorResponse", "properties", "status"],     id="auth-errorresponse-status"),
    # Financial Consolidation — DimensionProperty: name, flags, processingStatus, typeInfo restate field name/type
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "propertyName"],       id="fc-dimensionproperty-propertyname"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "reportingProperty"],  id="fc-dimensionproperty-reportingproperty"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "readonlyProperty"],   id="fc-dimensionproperty-readonlyproperty"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "processingStatus"],   id="fc-dimensionproperty-processingstatus"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty", "properties", "typeInfo"],           id="fc-dimensionproperty-typeinfo"),
    # Financial Consolidation — Dimension schema and its self-evident properties
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension"],                                              id="fc-dimension-schema"),
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "dimensionName"],              id="fc-dimension-dimensionname"),
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "dimensionType"],              id="fc-dimension-dimensiontype"),
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "relatedDimension"],           id="fc-dimension-relateddimension"),
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "properties"],                 id="fc-dimension-properties"),
    pytest.param("financial-consolidation", ["components", "schemas", "Dimension", "properties", "processingStatus"],           id="fc-dimension-processingstatus"),
    # Financial Consolidation — DimensionProperty schema-level description restates the name
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionProperty"],                                     id="fc-dimensionproperty-schema"),
    # Financial Consolidation — DimensionMember self-evident properties
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember"],                                       id="fc-dimensionmember-schema"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "memberName"],           id="fc-dimensionmember-membername"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "memberTag"],            id="fc-dimensionmember-membertag"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "memberCaption"],        id="fc-dimensionmember-membercaption"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "parentMemberName"],     id="fc-dimensionmember-parentmembername"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "sortOrder"],            id="fc-dimensionmember-sortorder"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "operator"],             id="fc-dimensionmember-operator"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMember", "properties", "memberStorage"],        id="fc-dimensionmember-memberstorage"),
    # Financial Consolidation — DimensionMembersResponse pagination fields are self-evident
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMembersResponse", "properties", "dimensionMembers"], id="fc-dimensionmembersresponse-dimensionmembers"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMembersResponse", "properties", "totalRows"],        id="fc-dimensionmembersresponse-totalrows"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMembersResponse", "properties", "currentPage"],      id="fc-dimensionmembersresponse-currentpage"),
    pytest.param("financial-consolidation", ["components", "schemas", "DimensionMembersResponse", "properties", "totalPages"],       id="fc-dimensionmembersresponse-totalpages"),
    # Financial Consolidation — User and UserInput self-evident fields
    pytest.param("financial-consolidation", ["components", "schemas", "User"],                                                  id="fc-user-schema"),
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "fullName"],                        id="fc-user-fullname"),
    pytest.param("financial-consolidation", ["components", "schemas", "User", "properties", "roles"],                           id="fc-user-roles"),
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput"],                                              id="fc-userinput-schema"),
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput", "properties", "fullName"],                    id="fc-userinput-fullname"),
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput", "properties", "isDisabled"],                  id="fc-userinput-isdisabled"),
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput", "properties", "email"],                       id="fc-userinput-email"),
    pytest.param("financial-consolidation", ["components", "schemas", "UserInput", "properties", "roles"],                       id="fc-userinput-roles"),
    # OAuth — grant_type: single-value enums are self-documenting; description restates the enum value (ADR 0003 §3)
    pytest.param("oauth", ["components", "schemas", "AuthCodePayload", "properties", "grant_type"],   id="oauth-authcodepayload-grant_type"),
    pytest.param("oauth", ["components", "schemas", "DevicePayload", "properties", "grant_type"],     id="oauth-devicepayload-grant_type"),
    pytest.param("oauth", ["components", "schemas", "RefreshPayload", "properties", "grant_type"],    id="oauth-refreshpayload-grant_type"),
    # OAuth — TokenResponse.token_type: enum [Bearer] already expresses the value; description restates it
    pytest.param("oauth", ["components", "schemas", "TokenResponse", "properties", "token_type"],     id="oauth-tokenresponse-token_type"),
    # OAuth — ErrorPayload.error_description: field name already expresses 'description of the error'
    pytest.param("oauth", ["components", "schemas", "ErrorPayload", "properties", "error_description"], id="oauth-errorpayload-error_description"),
    # SCIM User.name sub-fields — familyName/givenName restate the field name; name + type is sufficient
    pytest.param("scim", ["components", "schemas", "User", "properties", "name", "properties", "familyName"], id="scim-user-name-familyname"),
    pytest.param("scim", ["components", "schemas", "User", "properties", "name", "properties", "givenName"],  id="scim-user-name-givenname"),
    # SCIM User.emails.items.primary — boolean field name is self-evident in an emails array context
    pytest.param("scim", ["components", "schemas", "User", "properties", "emails", "items", "properties", "primary"], id="scim-user-emails-primary"),
    # SCIM User.meta — "Resource metadata." restates the field name
    pytest.param("scim", ["components", "schemas", "User", "properties", "meta"], id="scim-user-meta"),
    # SCIM PatchOp.Operations.items.op — "Operation type." restates the name; enum [add, remove, replace] is self-documenting
    pytest.param("scim", ["components", "schemas", "PatchOp", "properties", "Operations", "items", "properties", "op"], id="scim-patchop-op"),
    # Exception — ExceptionUserWorkspaceResult properties: field names are self-evident in a workspace-result context
    pytest.param("exception", ["components", "schemas", "ExceptionUserWorkspaceResult", "properties", "workspaceGuid"], id="exc-workspaceresult-workspaceguid"),
    pytest.param("exception", ["components", "schemas", "ExceptionUserWorkspaceResult", "properties", "workspaceName"], id="exc-workspaceresult-workspacename"),
    pytest.param("exception", ["components", "schemas", "ExceptionUserWorkspaceResult", "properties", "users"],         id="exc-workspaceresult-users"),
    # Exception — ExceptionUser properties: userGuid and email (format:email) are self-evident from name + type
    pytest.param("exception", ["components", "schemas", "ExceptionUser", "properties", "userGuid"], id="exc-exceptionuser-userguid"),
    pytest.param("exception", ["components", "schemas", "ExceptionUser", "properties", "email"],    id="exc-exceptionuser-email"),
    # Exception — ErrorResponse schema: the name is self-evident; provenance note belongs in README not the description
    pytest.param("exception", ["components", "schemas", "ErrorResponse"], id="exc-errorresponse-schema"),
    # Integration User — schema name is self-evident; all property descriptions restate the field name
    pytest.param("integration", ["components", "schemas", "User"],                                          id="int-user-schema"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "id"],                     id="int-user-id"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "firstName"],              id="int-user-firstname"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "lastName"],               id="int-user-lastname"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "email"],                  id="int-user-email"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "active"],                 id="int-user-active"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "lastLoginDate"],          id="int-user-lastlogindate"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "emailOptIn"],             id="int-user-emailoptin"),
    pytest.param("integration", ["components", "schemas", "User", "properties", "customerId"],             id="int-user-customerid"),
    # Integration Model — all field descriptions literally copy the field name; name + type already say it all
    pytest.param("integration", ["components", "schemas", "Model"],                                                          id="int-model-schema"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "id"],                                     id="int-model-id"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "name"],                                   id="int-model-name"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "activeState"],                            id="int-model-activestate"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "currentWorkspaceId"],                     id="int-model-currentworkspaceid"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "currentWorkspaceName"],                   id="int-model-currentworkspacename"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "modelUrl"],                               id="int-model-modelurl"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "isoCreationDate"],                        id="int-model-isocreationdate"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "lastModified"],                           id="int-model-lastmodified"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "lastModifiedByUserGuid"],                 id="int-model-lastmodifiedbyuserguid"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "lastSavedSerialNumber"],                  id="int-model-lastsavedserialnumber"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "memoryUsage"],                            id="int-model-memoryusage"),
    pytest.param("integration", ["components", "schemas", "Model", "properties", "modelTransactionRunning"],                id="int-model-modeltransactionrunning"),
    # Integration Workspace — schema name self-evident; all property descriptions restate the name
    pytest.param("integration", ["components", "schemas", "Workspace"],                                              id="int-workspace-schema"),
    pytest.param("integration", ["components", "schemas", "Workspace", "properties", "id"],                         id="int-workspace-id"),
    pytest.param("integration", ["components", "schemas", "Workspace", "properties", "name"],                       id="int-workspace-name"),
    pytest.param("integration", ["components", "schemas", "Workspace", "properties", "active"],                     id="int-workspace-active"),
    pytest.param("integration", ["components", "schemas", "Workspace", "properties", "sizeAllowance"],              id="int-workspace-sizeallowance"),
    pytest.param("integration", ["components", "schemas", "Workspace", "properties", "currentSize"],                id="int-workspace-currentsize"),
    # Integration — self-evident schema names whose descriptions restate the name without adding value
    pytest.param("integration", ["components", "schemas", "CurrentPeriod"],   id="int-currentperiod-schema"),
    pytest.param("integration", ["components", "schemas", "ModelCalendar"],   id="int-modelcalendar-schema"),
    pytest.param("integration", ["components", "schemas", "Module"],          id="int-module-schema"),
    pytest.param("integration", ["components", "schemas", "View"],            id="int-view-schema"),
    pytest.param("integration", ["components", "schemas", "Dimension"],       id="int-dimension-schema"),
    pytest.param("integration", ["components", "schemas", "List"],            id="int-list-schema"),
    pytest.param("integration", ["components", "schemas", "Export"],          id="int-export-schema"),
    pytest.param("integration", ["components", "schemas", "Import"],          id="int-import-schema"),
    pytest.param("integration", ["components", "schemas", "LineItem"],        id="int-lineitem-schema"),
    pytest.param("integration", ["components", "schemas", "Period"],          id="int-period-schema"),
    pytest.param("integration", ["components", "schemas", "ExportMetadata"],  id="int-exportmetadata-schema"),
    pytest.param("integration", ["components", "schemas", "Process"],         id="int-process-schema"),
]


@pytest.mark.parametrize("api_dir,path", _MUST_NOT_HAVE_DESCRIPTION)
def test_description_is_absent(api_dir, path):
    """Self-evident fields must not carry a description (ADR 0003 §2, §3).

    A tautological description is worse than no description: it trains both
    human readers and LLM code generators to ignore descriptions, obscuring
    the ones that actually matter.
    """
    spec = _load(api_dir)
    obj = _navigate(spec, path)
    assert obj is not None, f"{api_dir}: object not found at {'.'.join(path)}"
    assert "description" not in obj, (
        f"{api_dir}: {'.'.join(path)} must NOT have a 'description' key — "
        f"the field is self-evident from its name and type (ADR 0003 §2). "
        f"Remove the description; found: {obj.get('description')!r}"
    )


# ─── CloudWorks-specific: IntegrationDetail allOf sub-properties ─────────────
# IntegrationDetail uses allOf to extend IntegrationSummary. Its own properties
# live in allOf[1], which can't be reached by the generic _navigate helper above.

_CW_SPEC = REPO_ROOT / "cloudworks" / "cloudworks-openapi.json"
_skip_cw = pytest.mark.skipif(not _CW_SPEC.exists(), reason="CloudWorks spec not found")


@_skip_cw
@pytest.mark.parametrize("field", ["version", "jobs"])
def test_cloudworks_integrationdetail_allof_property_has_description(field):
    """IntegrationDetail allOf inline properties must have descriptions (ADR 0003 §2).

    'version' and 'jobs' are not self-evident: version could mean API version
    or schema version; jobs is absent on process integrations.
    """
    spec = json.loads(_CW_SPEC.read_text(encoding="utf-8"))
    allof = (
        spec.get("components", {})
        .get("schemas", {})
        .get("IntegrationDetail", {})
        .get("allOf", [])
    )
    inline = next((s for s in allof if "properties" in s), None)
    assert inline is not None, (
        "IntegrationDetail.allOf must contain an inline object with 'properties'"
    )
    prop = inline.get("properties", {}).get(field)
    assert prop is not None, f"IntegrationDetail must define '{field}' property in allOf"
    assert prop.get("description", "").strip(), (
        f"IntegrationDetail.{field} must have a description (ADR 0003 §2)"
    )


# ─── CloudWorks-specific: NotificationRequest config type ────────────────────
# Nested three levels deep; the generic parametrize would produce an
# unreadably long path so a named test is clearer.

@_skip_cw
def test_cloudworks_notification_config_type_has_description():
    """NotificationRequest.notifications.config[].type must explain the trigger conditions.

    The enum values (success, partial_failure, full_failure) state the condition
    but not what happens when it fires. A description is needed.
    """
    spec = json.loads(_CW_SPEC.read_text(encoding="utf-8"))
    type_prop = (
        spec.get("components", {})
        .get("schemas", {})
        .get("NotificationRequest", {})
        .get("properties", {})
        .get("notifications", {})
        .get("properties", {})
        .get("config", {})
        .get("items", {})
        .get("properties", {})
        .get("type", {})
    )
    assert type_prop, (
        "NotificationRequest.notifications.config[].type not found in spec"
    )
    assert type_prop.get("description", "").strip(), (
        "NotificationRequest.notifications.config[].type must have a description "
        "explaining that each entry triggers a notification on that outcome "
        "(ADR 0003 §3: enum descriptions explain behavior, not just values)"
    )


# ─── Enum-restatement description sweep ───────────────────────────────────────
#
# ADR 0003 §3: an enum lists valid values; a description must explain what those
# values *do*. If the description would only restate the enum values, omit it.
#
# Algorithm: a description is "purely enumerative" if
#   (1) it contains every enum value verbatim (case-insensitive, word-boundary),
#       AND
#   (2) after removing the enum values, the field name, the schema name, and a set
#       of filler words (articles, conjunctions, generic label words), nothing
#       substantive remains.
#
# A description that explains behavior — even if it names the values — is not a
# violation, because it leaves substantive tokens after stripping.

_ENUM_RESTATEMENT_FILLER = frozenset({
    "a", "an", "the", "is", "are", "be", "or", "and", "of", "in", "to",
    "for", "type", "value", "values", "possible", "valid", "one", "following",
    "can", "this", "field", "property", "parameter", "must", "may", "which",
    "either", "that", "with", "by", "it", "its", "as", "at", "on", "any",
    "these", "between", "list", "types", "kinds", "where", "used", "when",
    "such", "each", "per", "all", "if", "s",
})


def _is_enum_restatement(
    field_name: str,
    description: str,
    enum_values: list,
    schema_name: str = "",
) -> bool:
    """Return True if description adds nothing beyond listing the enum values."""
    if not description.strip() or not enum_values:
        return False

    def _norm(s: str) -> str:
        s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
        return re.sub(r"\s+", " ", s).strip()

    norm_desc = _norm(description)

    # Criterion 1: description must contain every enum value; otherwise it cannot
    # be a pure restatement of them.
    for val in enum_values:
        norm_val = _norm(str(val))
        if not norm_val:
            continue
        tokens = norm_val.split()
        pattern = r"\b" + r"\s+".join(re.escape(t) for t in tokens) + r"\b"
        if not re.search(pattern, norm_desc):
            return False

    # Criterion 2: strip enum values (longest first), field/schema name tokens,
    # and filler; if nothing substantive remains → violation.
    work = norm_desc
    for val in sorted(enum_values, key=lambda v: len(str(v)), reverse=True):
        norm_val = _norm(str(val))
        if norm_val:
            tokens = norm_val.split()
            pattern = r"\b" + r"\s+".join(re.escape(t) for t in tokens) + r"\b"
            work = re.sub(pattern, " ", work)

    for token in _normalize_name(field_name).split():
        if token:
            work = re.sub(r"\b" + re.escape(token) + r"\b", " ", work)

    if schema_name:
        for token in _normalize_name(schema_name).split():
            if token:
                work = re.sub(r"\b" + re.escape(token) + r"\b", " ", work)

    remaining = [t for t in work.split() if t and t not in _ENUM_RESTATEMENT_FILLER]
    return len(remaining) == 0


def _walk_enum_props(path: str, obj: dict) -> Iterator[tuple[str, str, list, str]]:
    """Yield (json_path, field_name, enum_values, description) for enum+description fields."""
    if not isinstance(obj, dict):
        return
    for prop_name, prop_obj in obj.get("properties", {}).items():
        if not isinstance(prop_obj, dict):
            continue
        prop_path = f"{path}/properties/{prop_name}"
        enum_vals = prop_obj.get("enum")
        desc = prop_obj.get("description", "")
        if enum_vals and desc:
            yield prop_path, prop_name, enum_vals, desc
        yield from _walk_enum_props(prop_path, prop_obj)
    for combiner in ("allOf", "anyOf", "oneOf"):
        for i, sub in enumerate(obj.get(combiner, [])):
            if isinstance(sub, dict):
                yield from _walk_enum_props(f"{path}/{combiner}/{i}", sub)
    if isinstance(obj.get("items"), dict):
        yield from _walk_enum_props(f"{path}/items", obj["items"])


def test_no_enum_restatement_descriptions():
    """No enum field may have a description that only restates its valid values (ADR 0003 §3).

    An enum lists valid values; a description must explain what those values *do*
    or add behavioral context the enum cannot express. A description like
    'Schedule type: weekly, daily, or hourly.' paired with enum [weekly, daily,
    hourly] adds nothing and must be omitted.

    A description that maps values to behavior — even if it names the values — is
    not a violation: 'assign grants access; unassign revokes it.' passes because
    'grants' and 'revokes' remain after stripping.
    """
    violations = []
    for api_dir in _ALL_API_DIRS:
        spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        schemas = spec.get("components", {}).get("schemas", {})
        for schema_name, schema_obj in schemas.items():
            if not isinstance(schema_obj, dict):
                continue
            for json_path, field_name, enum_vals, description in _walk_enum_props(
                f"components/schemas/{schema_name}", schema_obj
            ):
                if _is_enum_restatement(field_name, description, enum_vals, schema_name):
                    violations.append(
                        f"  [{api_dir}] {json_path}\n"
                        f"    enum:        {enum_vals!r}\n"
                        f"    description: {description!r}\n"
                        f"    (ADR 0003 §3: enum descriptions must explain what values do, "
                        f"not merely list them)"
                    )
    assert not violations, (
        f"{len(violations)} enum-restatement description(s) found\n"
        f"(ADR 0003 §3 — a description paired with an enum must explain what the values "
        f"do, not merely list them):\n"
        + "\n".join(violations)
    )


# ─── Tautological description sweep ───────────────────────────────────────────
#
# ADR 0003 §2: a description must earn its place. A description that merely
# restates the field or schema name is worse than no description — it trains
# readers to ignore descriptions, obscuring the ones that genuinely add value.
#
# This test sweeps all 9 specs automatically. No manual table entries needed.

_ALL_API_DIRS = [
    "alm",
    "audit",
    "authentication",
    "cloudworks",
    "exception",
    "financial-consolidation",
    "integration",
    "oauth",
    "scim",
]


def _normalize_name(name: str) -> str:
    """Convert camelCase/PascalCase/snake_case to lowercase space-separated words."""
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    return " ".join(name.lower().split())


def _normalize_desc(description: str) -> str:
    """Strip trailing period(s) and whitespace, lowercase."""
    return description.rstrip(".\t\n ").lower().strip()


def _is_tautological(field_name: str, description: str) -> bool:
    """Return True if description is a trivial restatement of field_name."""
    if not description.strip():
        return False
    norm_name = _normalize_name(field_name)
    norm_desc = _normalize_desc(description)
    if norm_desc == norm_name:
        return True
    # Trivial plural
    if norm_desc == norm_name + "s":
        return True
    # Leading article stripped
    for article in ("the ", "a ", "an "):
        if norm_desc.startswith(article):
            stripped = norm_desc[len(article):]
            if stripped == norm_name or stripped == norm_name + "s":
                return True
    return False


def _walk_obj(path: str, obj: dict) -> Iterator[tuple[str, str, str]]:
    """Recursively yield (json_path, field_name, description) for all properties."""
    if not isinstance(obj, dict):
        return
    for prop_name, prop_obj in obj.get("properties", {}).items():
        if not isinstance(prop_obj, dict):
            continue
        prop_path = f"{path}/properties/{prop_name}"
        desc = prop_obj.get("description", "")
        if desc:
            yield prop_path, prop_name, desc
        yield from _walk_obj(prop_path, prop_obj)
    for combiner in ("allOf", "anyOf", "oneOf"):
        for i, sub in enumerate(obj.get(combiner, [])):
            if isinstance(sub, dict):
                yield from _walk_obj(f"{path}/{combiner}/{i}", sub)
    items = obj.get("items")
    if isinstance(items, dict):
        yield from _walk_obj(f"{path}/items", items)


def _scheme_description_sentences(desc: str, min_len: int = 40) -> list[str]:
    """Extract sentences from a scheme description that are long enough to be distinctive."""
    sentences = re.split(r"(?<=[.!?])\s+", desc.strip())
    return [s.strip() for s in sentences if len(s.strip()) >= min_len]


def test_no_auth_detail_duplication():
    """info.description must not reproduce auth detail already in securitySchemes (ADR 0003 §4).

    securitySchemes is the single authoritative location for auth scheme detail.
    info.description may contain a one-line summary per scheme and cross-cutting
    behavioral notes, but must not repeat the full header format, token type,
    or accepted-values detail that already lives in securitySchemes.
    """
    violations = []
    for api_dir in _ALL_API_DIRS:
        spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        info_desc = spec.get("info", {}).get("description", "")
        if not info_desc:
            continue
        schemes = spec.get("components", {}).get("securitySchemes", {})
        if not schemes:
            continue
        for scheme_name, scheme_obj in schemes.items():
            scheme_desc = scheme_obj.get("description", "")
            if not scheme_desc:
                continue
            for sentence in _scheme_description_sentences(scheme_desc):
                if sentence.lower() in info_desc.lower():
                    violations.append(
                        f"  [{api_dir}] securitySchemes/{scheme_name}: info.description "
                        f"contains verbatim sentence from scheme description:\n"
                        f"    {sentence!r}\n"
                        f"    (ADR 0003 §4: securitySchemes is the single authoritative "
                        f"location for auth scheme detail; info.description may only "
                        f"contain a one-line summary per scheme and cross-cutting "
                        f"behavioral notes)"
                    )
    assert not violations, (
        f"{len(violations)} auth-detail duplication(s) found in info.description\n"
        f"(ADR 0003 §4 — full auth detail belongs exclusively in securitySchemes; "
        f"info.description may have a one-line summary per scheme and cross-cutting "
        f"behavioral notes only):\n"
        + "\n".join(violations)
    )


# ─── Unconfirmed pattern constraint sweep ────────────────────────────────────
#
# ADR 0003 §5: a speculative pattern on an Anaplan ID field that turns out to be
# wrong is a regression — generated validators will reject valid input.
# Patterns are only safe once confirmed via live testing.
#
# Any pattern already present in the 9 specs at the time this rule was adopted
# is grandfathered in tests/confirmed_patterns.json.  Every new pattern added to
# a spec must be accompanied by a matching entry in that file, which serves as the
# paper trail that live testing occurred.

_CONFIRMED_PATTERNS_PATH = REPO_ROOT / "tests" / "confirmed_patterns.json"


def _load_confirmed_patterns() -> frozenset[tuple[str, str, str]]:
    if not _CONFIRMED_PATTERNS_PATH.exists():
        return frozenset()
    entries = json.loads(_CONFIRMED_PATTERNS_PATH.read_text(encoding="utf-8"))
    return frozenset((e["spec"], e["path"], e["pattern"]) for e in entries)


def _walk_all_patterns(spec: dict) -> list[tuple[str, str]]:
    """Return (json_path, pattern) for every `pattern` key in the spec."""
    results: list[tuple[str, str]] = []

    def _recurse(path: str, obj: object) -> None:
        if not isinstance(obj, dict):
            return
        if "pattern" in obj:
            results.append((path, obj["pattern"]))
        for k, v in obj.items():
            if k == "pattern":
                continue
            if isinstance(v, dict):
                _recurse(f"{path}/{k}", v)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        _recurse(f"{path}/{k}/{i}", item)

    _recurse("", spec)
    return results


def test_no_unconfirmed_patterns():
    """Every pattern constraint in the 9 specs must appear in confirmed_patterns.json (ADR 0003 §5).

    A speculative pattern that turns out to be wrong causes generated validators
    to reject valid Anaplan API responses — a silent regression.  Patterns are
    only safe once confirmed via live testing.

    To add a new pattern: run the relevant live test to confirm the constraint,
    then add an entry to tests/confirmed_patterns.json with keys spec, path, and
    pattern.  See ADR 0003 §5 for the full rationale.
    """
    confirmed = _load_confirmed_patterns()
    violations = []
    for api_dir in _ALL_API_DIRS:
        spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for json_path, pattern in _walk_all_patterns(spec):
            if (api_dir, json_path, pattern) not in confirmed:
                violations.append(
                    f"  [{api_dir}] {json_path}\n"
                    f"    pattern: {pattern!r}\n"
                    f"    (ADR 0003 §5: pattern constraints must be confirmed via live "
                    f"testing before being added to the spec.  Add an entry to "
                    f"tests/confirmed_patterns.json with keys 'spec', 'path', and "
                    f"'pattern' only after live-test confirmation.)"
                )
    assert not violations, (
        f"{len(violations)} unconfirmed pattern constraint(s) found\n"
        f"(ADR 0003 §5 — each entry in confirmed_patterns.json is the paper trail "
        f"that live testing occurred; do not add entries without running the live tests):\n"
        + "\n".join(violations)
    )


# ─── Confirmed-history provenance note sweep ─────────────────────────────────
#
# ADR 0003 §6: once a field name or value is confirmed via live testing, any
# provenance note ("Apiary called this X; confirmed via live testing is Y",
# "live testing showed Z") must move to api/README.md under "Discrepancies".
# Only unconfirmed-field warnings ("not yet validated via live testing") may
# remain in descriptions.
#
# This sweep covers the full JSON tree — info, servers, paths, parameters,
# responses, securitySchemes, and component schemas — not just schemas.
#
# Case-sensitive patterns for proper nouns so that lowercase occurrences in
# cross-reference URLs (apiary.io, postman.com) are not flagged.

def _walk_all_descriptions(obj: object, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield (json_path, description_text) for every 'description' string in the spec."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}/{key}" if path else key
            if key == "description" and isinstance(value, str):
                yield child_path, value
            else:
                yield from _walk_all_descriptions(value, child_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk_all_descriptions(item, f"{path}/{i}")


_PROVENANCE_NOUN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bApiary\b"), "Apiary"),
    (re.compile(r"\bPostman\b"), "Postman"),
]

_PROVENANCE_PHRASE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bconfirmed\b", re.IGNORECASE), "confirmed"),
    (re.compile(r"\blive\s+test(?:ing|ed)\b", re.IGNORECASE), "live testing"),
    (re.compile(r"\bpreviously\s+called\b", re.IGNORECASE), "previously called"),
]

_PROVENANCE_NEGATION = re.compile(
    r"\b(?:not|n't|never|hasn't|haven't)\b", re.IGNORECASE
)
_NEGATION_WINDOW = 50


def _find_provenance_phrase(description: str) -> str | None:
    """Return the first confirmed-history phrase found, or None if none found."""
    for pattern, label in _PROVENANCE_NOUN_PATTERNS:
        if pattern.search(description):
            return label
    for pattern, label in _PROVENANCE_PHRASE_PATTERNS:
        for match in pattern.finditer(description):
            window = description[max(0, match.start() - _NEGATION_WINDOW):match.start()]
            if not _PROVENANCE_NEGATION.search(window):
                return f"{label} (matched {match.group()!r})"
    return None


def test_no_confirmed_history_provenance_notes():
    """No description may contain confirmed-history provenance notes (ADR 0003 §6).

    Once a field name or value is confirmed via live testing, the provenance note
    must move to api/README.md under 'Discrepancies'. Only unconfirmed-field
    warnings ('Field name unconfirmed — not yet validated via live testing') may
    remain in descriptions.

    Failure messages include: spec name, JSON path, matching phrase, and a
    citation of ADR 0003 §6 with instruction to move the note to the README.
    """
    violations = []
    for api_dir in _ALL_API_DIRS:
        spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for json_path, description in _walk_all_descriptions(spec):
            phrase = _find_provenance_phrase(description)
            if phrase is not None:
                violations.append(
                    f"  [{api_dir}] {json_path}\n"
                    f"    matched: {phrase!r}\n"
                    f"    (ADR 0003 §6: confirmed-history provenance notes belong in "
                    f"{api_dir}/README.md under 'Discrepancies', not in descriptions)"
                )
    assert not violations, (
        f"{len(violations)} confirmed-history provenance note(s) found in descriptions\n"
        f"(ADR 0003 §6 — once a field name or value is confirmed via live testing, "
        f"the provenance note must move to api/README.md under 'Discrepancies'):\n"
        + "\n".join(violations)
    )


def test_no_tautological_descriptions():
    """No schema or property may have a description that merely restates its name (ADR 0003 §2).

    A tautological description ('Integration ID.', 'Job type.') is worse than
    no description: it trains readers — both human and LLM — to ignore all
    descriptions, obscuring the ones that genuinely add value.
    """
    violations = []
    for api_dir in _ALL_API_DIRS:
        spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        schemas = spec.get("components", {}).get("schemas", {})
        for schema_name, schema_obj in schemas.items():
            if not isinstance(schema_obj, dict):
                continue
            # Schema-level description vs schema name
            desc = schema_obj.get("description", "")
            if desc and _is_tautological(schema_name, desc):
                violations.append(
                    f"  [{api_dir}] components/schemas/{schema_name}: "
                    f"schema description restates its name — {desc!r} (ADR 0003 §2)"
                )
            # Property-level descriptions vs property names (recursive)
            for json_path, field_name, description in _walk_obj(
                f"components/schemas/{schema_name}", schema_obj
            ):
                if _is_tautological(field_name, description):
                    violations.append(
                        f"  [{api_dir}] {json_path}: "
                        f"description of {field_name!r} restates its name — "
                        f"{description!r} (ADR 0003 §2)"
                    )
    assert not violations, (
        f"{len(violations)} tautological description(s) found "
        f"(ADR 0003 §2 — a description must say something the field name does not):\n"
        + "\n".join(violations)
    )
