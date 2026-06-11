from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    environment: str = Field(default="production", alias="ENVIRONMENT")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    stateless_http: bool = Field(default=True, alias="FASTMCP_STATELESS_HTTP")

    # MCP auth (Claude → this server)
    mcp_api_key: str = Field(default="", alias="MCP_API_KEY")
    mcp_auth_token: str = Field(default="", alias="MCP_AUTH_TOKEN")

    # Vtiger connection
    vtiger_base_url: str = Field(default="", alias="VTIGER_BASE_URL")
    vtiger_username: str = Field(default="", alias="VTIGER_USERNAME")
    vtiger_access_key: str = Field(default="", alias="VTIGER_ACCESS_KEY")
    vtiger_request_timeout_seconds: float = Field(
        default=30.0,
        alias="VTIGER_REQUEST_TIMEOUT_SECONDS",
    )
    vtiger_query_page_size: int = Field(default=100, alias="VTIGER_QUERY_PAGE_SIZE")

    # Modules
    vtiger_leads_module: str = Field(default="Leads", alias="VTIGER_LEADS_MODULE")
    vtiger_deals_module: str = Field(default="Potentials", alias="VTIGER_DEALS_MODULE")

    # Lead field mapping (override after Natasha field-mapping session)
    vtiger_field_lead_owner: str = Field(
        default="assigned_user_id",
        alias="VTIGER_FIELD_LEAD_OWNER",
    )
    vtiger_field_lead_org: str = Field(default="company", alias="VTIGER_FIELD_LEAD_ORG")
    vtiger_field_lead_status: str = Field(
        default="leadstatus",
        alias="VTIGER_FIELD_LEAD_STATUS",
    )
    vtiger_field_lead_followup_date: str = Field(
        default="",
        alias="VTIGER_FIELD_LEAD_FOLLOWUP_DATE",
    )
    vtiger_field_lead_followup_desc: str = Field(
        default="",
        alias="VTIGER_FIELD_LEAD_FOLLOWUP_DESC",
    )

    # Deal field mapping
    vtiger_field_deal_owner: str = Field(
        default="assigned_user_id",
        alias="VTIGER_FIELD_DEAL_OWNER",
    )
    vtiger_field_deal_name: str = Field(
        default="potentialname",
        alias="VTIGER_FIELD_DEAL_NAME",
    )
    vtiger_field_deal_stage: str = Field(
        default="sales_stage",
        alias="VTIGER_FIELD_DEAL_STAGE",
    )
    vtiger_field_deal_amount: str = Field(default="amount", alias="VTIGER_FIELD_DEAL_AMOUNT")
    vtiger_field_deal_last_contacted: str = Field(
        default="",
        alias="VTIGER_FIELD_DEAL_LAST_CONTACTED",
    )
    vtiger_field_deal_followup_date: str = Field(
        default="",
        alias="VTIGER_FIELD_DEAL_FOLLOWUP_DATE",
    )
    vtiger_field_deal_followup_desc: str = Field(
        default="",
        alias="VTIGER_FIELD_DEAL_FOLLOWUP_DESC",
    )

    # Comma-separated open stages; empty = no stage filter
    vtiger_open_deal_stages: str = Field(default="", alias="VTIGER_OPEN_DEAL_STAGES")

    @field_validator("vtiger_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def vtiger_webservice_url(self) -> str:
        return f"{self.vtiger_base_url}/webservice.php"

    @property
    def open_deal_stage_list(self) -> list[str]:
        if not self.vtiger_open_deal_stages.strip():
            return []
        return [stage.strip() for stage in self.vtiger_open_deal_stages.split(",") if stage.strip()]

    def lead_select_fields(self) -> list[str]:
        fields = [
            "id",
            self.vtiger_field_lead_owner,
            self.vtiger_field_lead_org,
            self.vtiger_field_lead_status,
        ]
        if self.vtiger_field_lead_followup_date:
            fields.append(self.vtiger_field_lead_followup_date)
        if self.vtiger_field_lead_followup_desc:
            fields.append(self.vtiger_field_lead_followup_desc)
        return _dedupe(fields)

    def deal_select_fields(self) -> list[str]:
        fields = [
            "id",
            self.vtiger_field_deal_owner,
            self.vtiger_field_deal_name,
            self.vtiger_field_deal_stage,
            self.vtiger_field_deal_amount,
        ]
        if self.vtiger_field_deal_last_contacted:
            fields.append(self.vtiger_field_deal_last_contacted)
        if self.vtiger_field_deal_followup_date:
            fields.append(self.vtiger_field_deal_followup_date)
        if self.vtiger_field_deal_followup_desc:
            fields.append(self.vtiger_field_deal_followup_desc)
        return _dedupe(fields)


def _dedupe(fields: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for field in fields:
        if field and field not in seen:
            seen.add(field)
            ordered.append(field)
    return ordered


@lru_cache
def get_settings() -> Settings:
    return Settings()
