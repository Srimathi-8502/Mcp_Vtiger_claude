"""
Per-module field registry for the AM-facing query tools.

Each module has:
  - default_fields: returned when the AM's query doesn't name specific fields.
    Kept small on purpose so a vague query doesn't return a wide, mostly-empty
    payload. Source: Batch 1 module analysis docs.
  - all_fields: every field the tool will accept in `fields`, `filters`, or
    `order_by`. Anything not in this list is rejected before it reaches
    Vtiger. This is a safety allowlist, not a suggestion of what's useful.
  - owner_field: the field used to scope queries to the signed-in AM.

Fields known from Batch 1 to be entirely unpopulated or otherwise excluded
(see BATCH1_MASTER.md "Fields to exclude") are left out of all_fields
entirely, not just default_fields, so they can never be requested.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSpec:
    api_name: str
    owner_field: str | None
    default_fields: tuple[str, ...]
    all_fields: tuple[str, ...]


VTCMSLA = ModuleSpec(
    api_name="vtcmsla",
    owner_field="assigned_user_id",
    default_fields=(
        "id",
        "cf_vtcmsla_enddate",
        "cf_vtcmsla_organizationname",
        "cf_vtcmsla_sla",
        "cf_vtcmsla_status",
        "cf_vtcmsla_productdescription",
        "cf_vtcmsla_serialno",
        "cf_vtcmsla_oemsupport",
        "cf_vtcmsla_startdate",
    ),
    all_fields=(
        "id",
        "fld_vtcmslaname",
        "vtcmslanumber",
        "fld_sladate",
        "assigned_user_id",
        "created_user_id",
        "modifiedby",
        "createdtime",
        "modifiedtime",
        "source",
        "cf_vtcmsla_sla",
        "cf_vtcmsla_organizationname",
        "cf_vtcmsla_productdescription",
        "cf_vtcmsla_status",
        "cf_vtcmsla_uniwaresupportcategory",
        "cf_vtcmsla_invoice",
        "cf_vtcmsla_serialno",
        "cf_vtcmsla_oemsupport",
        "cf_vtcmsla_startdate",
        "cf_vtcmsla_enddate",
        "cf_vtcmsla_scopeofwork",
        # starred, record_currency_id, record_conversion_rate excluded: 0.0% filled
    ),
)

MODULES: dict[str, ModuleSpec] = {
    "vtcmsla": VTCMSLA,
}
