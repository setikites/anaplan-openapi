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
    # CloudWorks component parameters — name + example are sufficient;
    # 'Integration ID.' / 'Connection ID.' restate the name and add nothing.
    pytest.param("cloudworks", ["components", "parameters", "integrationId"],    id="cw-param-integrationid"),
    pytest.param("cloudworks", ["components", "parameters", "connectionId"],      id="cw-param-connectionid"),
    pytest.param("cloudworks", ["components", "parameters", "notificationId"],    id="cw-param-notificationid"),
    pytest.param("cloudworks", ["components", "parameters", "runId"],             id="cw-param-runid"),
    pytest.param("cloudworks", ["components", "parameters", "integrationFlowId"], id="cw-param-integrationflowid"),
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
