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
    org_field: str | None = None


VTCMSLA = ModuleSpec(
    api_name="vtcmsla",
    owner_field="assigned_user_id",
    org_field="cf_vtcmsla_organizationname",
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

POTENTIALS = ModuleSpec(
    api_name="Potentials",
    owner_field="assigned_user_id",
    org_field="related_to",
    default_fields=(
        "id",
        "potentialname",
        "forecast_amount",
        "amount",
        "cf_potentials_toplinevalue",
        "sales_stage",
        "current_stage_entry_time",
        "opportunity_type",
        "related_to",
        "contact_id",
        "assigned_user_id",
        "cf_potentials_coowners",
        "cf_potentials_coowners2",
        "closingdate",
        "probability",
        "createdtime",
        "cf_potentials_nextfollowupdate",
        "nextstep",
        "lost_reason",
        "leadsource",
        "cf_potentials_oem",
        "cf_potentials_region",
        "last_contacted_on",
    ),
    all_fields=(
        "id",
        "potentialname",
        "potential_no",
        "closingdate",
        "cf_potentials_nextfollowupdate",
        "sales_stage",
        "pipeline",
        "leadsource",
        "assigned_user_id",
        "opportunity_type",
        "cf_potentials_subcategoryofleadsource",
        "cf_potentials_subcategoryoftype",
        "modifiedby",
        "cf_potentials_region",
        "campaignid",
        "probability",
        "created_user_id",
        "createdtime",
        "modifiedtime",
        "last_contacted_on",
        "last_contacted_via",
        "isconvertedfromlead",
        "current_stage_entry_time",
        "source",
        "record_currency_id",
        "record_conversion_rate",
        "cf_potentials_oem",
        "cf_potentials_oemsubcategory",
        "cf_potentials_coowners",
        "cf_potentials_coowners2",
        "isclosed",
        "hdnSubTotal",
        "hdnGrandTotal",
        "contact_id",
        "related_to",
        "adjusted_amount",
        "adjusted_amount_currency_value",
        "amount",
        "forecast_amount",
        "journey_template_id",
        "items_sync_with",
        "cf_potentials_week",
        "forecast_category",
        "cf_potentials_toplinevalue",
        "cf_potentials_points",
        "lost_reason",
        "nextstep",
        "description",
        "cf_potentials_lostremarks",
        # Excluded entirely, 0.0% real value or 0.0% filled (BATCH1 section 9):
        # hdnDiscountAmount, hdnDiscountPercent, hdnS_H_Amount, calculus_revenue,
        # progress, calculus_score, fit_score, authority_score, engagement_score,
        # sentiment_score, productid, quantity, listprice, netprice,
        # discount_amount, discount_percent, section_name, section_no, comment,
        # pricebook_id, billing_type, hdnS_H_Percent, predicted_date,
        # opp_contactrole, next_journey, starred.
        # Potentials carries no line items; these are genuinely empty, not an
        # API artifact.
    ),
)

MODULES: dict[str, ModuleSpec] = {
    "vtcmsla": VTCMSLA,
    "Potentials": POTENTIALS,
}
