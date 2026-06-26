"""Generate MCP_Implementation.docx — single consolidated project documentation."""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx_helpers import (  # noqa: E402
    add_markdown_file,
    document_map,
    h,
    para,
    title_page,
)
from generate_complete_docx import add_stakeholder_sections  # noqa: E402

OUTPUT = ROOT / "MCP_Implementation.docx"


def add_technical_supplement(doc: Document) -> None:
    """Current-architecture notes (TECHNICAL.md predates OAuth tools)."""
    h(doc, "Architecture supplement — current OAuth implementation", 2)
    para(
        doc,
        "The following updates supersede any references in Part 3 to three owner-based "
        "tools (get_leads_by_owner, get_deals_by_owner, get_overdue_followups) or "
        "shared MCP_API_KEY as the primary auth model.",
    )
    from docx_helpers import numbered, table

    h(doc, "Current MCP tools (4)", 3)
    table(
        doc,
        ["Tool", "Auth", "Purpose"],
        [
            ["whoami", "OAuth required", "Signed-in email, Vtiger owner ID, admin flag, scope"],
            ["get_my_leads", "OAuth required", "Leads for signed-in AM (admin: all or am_email filter)"],
            ["get_my_deals", "OAuth required", "Deals for signed-in AM (admin: all or am_email filter)"],
            [
                "get_my_overdue_followups",
                "OAuth required",
                "Overdue deals/leads for signed-in AM (admin: all or am_email filter)",
            ],
        ],
    )

    h(doc, "Auth stack (production)", 3)
    numbered(doc, "Claude sends Bearer JWT from Microsoft Entra ID sign-in.")
    numbered(doc, "ApiKeyMiddleware passes JWT through (does not treat it as MCP_API_KEY).")
    numbered(doc, "FastMCP AzureProvider validates token.")
    numbered(doc, "auth/users.py maps email → Vtiger Users → owner_id.")
    numbered(doc, "VTIGER_ADMIN_EMAILS grants all-data scope (e.g. nirmal@uniware.net).")

    h(doc, "Module responsibilities", 3)
    table(
        doc,
        ["Module", "Responsibility"],
        [
            ["main.py", "FastMCP bootstrap, AzureProvider, /health, /ready"],
            ["config.py", "Settings, azure_oauth_enabled, field mapping"],
            ["middleware.py", "API key gate + JWT pass-through"],
            ["auth/users.py", "UserResolver, get_authenticated_user(), owner scope"],
            ["tools/crm.py", "whoami + get_my_* MCP tools"],
            ["vtiger/client.py", "Vtiger login, queries, normalization, session retry"],
            ["logging_config.py", "Stdout logging from LOG_LEVEL"],
        ],
    )

    h(doc, "OAuth-aware request flow", 3)
    numbered(doc, "AM enables Uniware Vtiger MCP connector in Claude and signs in with @uniware.net.")
    numbered(doc, "Claude POST /mcp with tool call (e.g. get_my_overdue_followups).")
    numbered(doc, "Azure OAuth validated; email extracted from token claims.")
    numbered(doc, "VtigerClient logs in and runs paginated queries scoped to owner_id.")
    numbered(doc, "Deals: related_to resolved to organisation_name via Accounts module.")
    numbered(doc, "JSON returned to Claude for natural-language briefing.")


def build() -> Document:
    doc = Document()

    title_page(
        doc,
        "Uniware Vtiger MCP — Complete Implementation",
        "Consolidated documentation\n"
        "Stakeholder guide · Project journey · Technical architecture · Claude + Entra ID setup\n"
        "June 2026 | Uniware GenAI Team",
    )

    document_map(
        doc,
        [
            ["Part 1", "Stakeholder implementation guide (requirements, architecture, security, deploy)"],
            ["Part 2", "Project journey & technical history (timeline, issues, solutions, modules)"],
            ["Part 3", "Technical architecture & request flow (docs/TECHNICAL.md)"],
            ["Part 4", "Claude connector + Microsoft Entra ID setup (docs/CLAUDE_SETUP.md)"],
        ],
    )

    h(doc, "Part 1 — Stakeholder Implementation Guide", 0)
    add_stakeholder_sections(doc, include_cover=False)

    doc.add_page_break()
    h(doc, "Part 2 — Project Journey & Technical History", 0)
    add_markdown_file(
        doc,
        ROOT / "docs" / "PROJECT_JOURNEY_AND_TECHNICAL_HISTORY.md",
        skip_title=True,
    )

    doc.add_page_break()
    h(doc, "Part 3 — Technical Architecture & Request Flow", 0)
    para(
        doc,
        "Source: docs/TECHNICAL.md. Diagram blocks (mermaid) appear as code. "
        "See the supplement below for the current OAuth tool set.",
    )
    add_markdown_file(doc, ROOT / "docs" / "TECHNICAL.md", skip_title=True)
    add_technical_supplement(doc)

    doc.add_page_break()
    h(doc, "Part 4 — Claude Connector & Microsoft Entra ID Setup", 0)
    add_markdown_file(doc, ROOT / "docs" / "CLAUDE_SETUP.md", skip_title=True)

    return doc


def main() -> None:
    doc = build()
    doc.save(OUTPUT)
    print(f"Created: {OUTPUT}")


if __name__ == "__main__":
    main()
