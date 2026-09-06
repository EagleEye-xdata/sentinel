"""
Tamper-evident PDF assessment report.

The PDF is a rendering of the same `build_report()` dictionary that backs the
JSON and Markdown exports -- one source of truth, three presentations. It closes
with the audit chain's verification stamp and head hash, so the document states
on its face whether the run it describes is still cryptographically intact.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

SEVERITY_COLORS = {
    "CRITICAL": "#b3123b",
    "HIGH": "#d1451c",
    "MEDIUM": "#b8860b",
    "LOW": "#1f7a4d",
}

OUTCOME_COLORS = {
    "SUCCESSFUL": "#b3123b",
    "RESISTED": "#1f7a4d",
    "INCONCLUSIVE": "#6b6b76",
    "ERROR": "#6b6b76",
    "SKIPPED_INCOMPATIBLE": "#6b6b76",
}


def available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def _clean(value: Any, limit: int = 1200) -> str:
    """Escape for reportlab's mini-markup and clamp length."""
    text = "" if value is None else str(value)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text[:limit] + ("…" if len(text) > limit else "")


def render_pdf(report: dict[str, Any], audit: dict[str, Any] | None = None,
               max_findings: int = 30) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"AI Security Assessment — {report.get('target_name', 'target')}",
        author="Sentinel — Unified AI Security Architecture v2",
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=21, leading=25,
                                textColor=colors.HexColor("#0d1b2a"), spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=10.5, leading=14,
                              textColor=colors.HexColor("#55606e")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, leading=16,
                             textColor=colors.HexColor("#123a6b"), spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=10.5, leading=13,
                             textColor=colors.HexColor("#0d1b2a"), spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.2, leading=12.6,
                               alignment=TA_LEFT),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, leading=10.5,
                                textColor=colors.HexColor("#55606e"), spaceAfter=3),
        "mono": ParagraphStyle("m", parent=base["Code"], fontSize=7.6, leading=9.8,
                               backColor=colors.HexColor("#f4f5f8"),
                               borderPadding=4, textColor=colors.HexColor("#1c2430")),
    }

    def table(data, widths, extra=None):
        t = Table(data, colWidths=widths, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123a6b")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.4),
            ("LEADING", (0, 0), (-1, -1), 11),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5dae3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        t.setStyle(TableStyle(style + (extra or [])))
        return t

    totals = report.get("totals", {})
    executed = max(1, totals.get("executed", 0))
    risk = report.get("risk_score_overall", 0)
    posture = ("CRITICAL" if risk >= 80 else "HIGH" if risk >= 60
               else "MODERATE" if risk >= 30 else "LOW")
    posture_color = colors.HexColor(
        "#b3123b" if posture == "CRITICAL" else "#d1451c" if posture == "HIGH"
        else "#b8860b" if posture == "MODERATE" else "#1f7a4d")

    story: list[Any] = []

    # ---------------------------------------------------------------- cover
    story.append(Paragraph("AI Security Assessment Report", styles["title"]))
    story.append(Paragraph(
        f"Sentinel — Unified AI Security Architecture v2 · run #{report.get('run_id')} · "
        f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", styles["sub"]))
    story.append(Spacer(1, 10))

    story.append(table(
        [["Target", _clean(report.get("target_name"), 90)],
         ["Assessment status", _clean(str(report.get("status", "")).upper(), 40)],
         ["Overall risk score", f"{risk} / 100"],
         ["Security posture", posture],
         ["Detection engine", "zero-API deterministic fusion — (0.50 x R) + (0.35 x S) + (0.15 x D)"]],
        [38 * mm, 136 * mm],
        extra=[("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f5f8")),
               ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
               ("TEXTCOLOR", (1, 3), (1, 3), posture_color),
               ("FONTNAME", (1, 3), (1, 3), "Helvetica-Bold")]))
    story.append(Spacer(1, 12))

    # ----------------------------------------------------- executive summary
    story.append(Paragraph("1. Executive summary", styles["h2"]))
    pct = lambda n: f"{n} ({round(n / executed * 100, 1)}%)"  # noqa: E731
    story.append(table(
        [["Metric", "Count", "Meaning"],
         ["Attacks executed", str(totals.get("executed", 0)), "Payloads dispatched through the gateway"],
         ["Successful breaches", pct(totals.get("successful", 0)), "Target followed the injection or leaked protected data"],
         ["Resisted", pct(totals.get("resisted", 0)), "Target refused and held its policy"],
         ["Inconclusive", str(totals.get("inconclusive", 0)), "No explicit refusal and no detectable leak"],
         ["Skipped / errors", str(totals.get("skipped_incompatible", 0) + totals.get("errors", 0)), "Capability mismatch or transport failure"]],
        [40 * mm, 26 * mm, 108 * mm]))
    story.append(Spacer(1, 6))

    sev = report.get("severity_breakdown", {})
    if sev:
        story.append(Paragraph("Derived severity distribution", styles["h3"]))
        story.append(table(
            [["Severity", "Findings"]] + [[k.upper(), str(v)] for k, v in sorted(sev.items(), key=lambda kv: -kv[1])],
            [40 * mm, 30 * mm]))

    # ------------------------------------------------------------- coverage
    story.append(Paragraph("2. Coverage by OWASP LLM Top 10", styles["h2"]))
    owasp_rows = [["Classification", "Tested", "Breached", "Resisted"]]
    for row in report.get("by_owasp", []):
        owasp_rows.append([_clean(row["owasp"], 70), str(row.get("executed", 0)),
                           str(row.get("successful", 0)), str(row.get("resisted", 0))])
    story.append(table(owasp_rows, [98 * mm, 22 * mm, 26 * mm, 26 * mm]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Coverage by attack category", styles["h3"]))
    cat_rows = [["Category", "Executed", "Breached", "Resisted"]]
    for row in sorted(report.get("by_category", []), key=lambda r: -r.get("successful", 0)):
        cat_rows.append([_clean(row["category"], 50), str(row.get("executed", 0)),
                         str(row.get("successful", 0)), str(row.get("resisted", 0))])
    story.append(table(cat_rows, [98 * mm, 22 * mm, 26 * mm, 26 * mm]))

    # ------------------------------------------------------------- findings
    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Ranked findings", styles["h2"]))
    story.append(Paragraph(
        "Findings are ordered by outcome then confidence. Each entry carries the exact payload, the "
        "gateway verdict, the observed response excerpt, and the remediation for that attack class.",
        styles["small"]))
    story.append(Spacer(1, 6))

    findings = report.get("findings", [])[:max_findings]
    if not findings:
        story.append(Paragraph("No executions were recorded for this run.", styles["body"]))

    for index, finding in enumerate(findings, 1):
        outcome = finding.get("outcome", "INCONCLUSIVE")
        block = [
            Paragraph(
                f'<font color="{OUTCOME_COLORS.get(outcome, "#6b6b76")}"><b>[{_clean(outcome, 30)}]</b></font> '
                f'{index}. {_clean(finding.get("title"), 110)}', styles["h3"]),
            table(
                [["Category", _clean(finding.get("category"), 40),
                  "Severity", _clean(finding.get("derived_severity"), 12)],
                 ["OWASP", _clean(finding.get("owasp_tag"), 46),
                  "Confidence", str(finding.get("confidence", 0))],
                 ["Request gate", _clean(finding.get("request_verdict"), 12),
                  "Reached target", str(finding.get("reached_target"))]],
                [24 * mm, 68 * mm, 26 * mm, 56 * mm],
                extra=[("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f5f8")),
                       ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f4f5f8")),
                       ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                       ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                       ("TEXTCOLOR", (3, 0), (3, 0),
                        colors.HexColor(SEVERITY_COLORS.get(finding.get("derived_severity", "LOW"), "#1f7a4d")))]),
            Spacer(1, 3),
            Paragraph("<b>Payload</b>", styles["small"]),
            Paragraph(_clean(finding.get("payload_used"), 700), styles["mono"]),
            Spacer(1, 3),
            Paragraph("<b>Observed response</b>", styles["small"]),
            Paragraph(_clean(finding.get("response_excerpt") or "(no response — blocked at the gateway)", 700), styles["mono"]),
            Spacer(1, 3),
            Paragraph(f'<b>Remediation:</b> {_clean(finding.get("remediation"), 600)}', styles["body"]),
            Spacer(1, 9),
        ]
        story.append(KeepTogether(block) if len(findings) > 1 else block[0])
        for element in (block[1:] if len(findings) == 1 else []):
            story.append(element)

    if len(report.get("findings", [])) > max_findings:
        story.append(Paragraph(
            f"{len(report['findings']) - max_findings} further findings are included in the JSON and "
            f"Markdown exports of this run.", styles["small"]))

    # --------------------------------------------------------- audit stamp
    story.append(PageBreak())
    story.append(Paragraph("4. Cryptographic audit stamp", styles["h2"]))
    if audit:
        valid = audit.get("valid")
        stamp = "CHAIN INTACT" if valid else "CHAIN BROKEN"
        stamp_color = "#1f7a4d" if valid else "#b3123b"
        story.append(Paragraph(
            f'<font color="{stamp_color}" size="13"><b>{stamp}</b></font>', styles["body"]))
        story.append(Spacer(1, 5))
        rows = [["Property", "Value"],
                ["Algorithm", _clean(audit.get("algorithm", "HMAC-SHA256"), 30)],
                ["Entries in chain", str(audit.get("entries", 0))],
                ["Entries verified", str(audit.get("verified", 0))],
                ["Head hash", _clean(audit.get("head_hash"), 70)]]
        if not valid:
            rows.append(["First corrupted seq", str(audit.get("corrupted_seq"))])
            rows.append(["Reason", _clean(audit.get("reason"), 60)])
        story.append(table(rows, [40 * mm, 134 * mm],
                           extra=[("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f5f8")),
                                  ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
        story.append(Spacer(1, 5))
        story.append(Paragraph(
            "Every gateway decision in this run was appended to an HMAC-SHA256 authenticated hash chain. "
            "When the run completed the segment key was published atomically, which freezes the segment: "
            "the published record commits to the head hash above, so any later edit to a decision row is "
            "detectable by re-walking the chain with the published key.", styles["small"]))
    else:
        story.append(Paragraph("Audit verification was not requested for this export.", styles["body"]))

    # -------------------------------------------------------- limitations
    story.append(Paragraph("5. Declared limitations", styles["h2"]))
    for line in [
        "Content the target fetches itself (server-side RAG or browsing) is outside proxy scope unless it "
        "surfaces in the response body.",
        "Internal tool calls that never appear in the response cannot be observed by a response-side gate.",
        "Payloads split across more turns than the session window retains are not reassembled.",
        "Runs against the deterministic sandbox oracle demonstrate pipeline correctness, not detection "
        "generality against production models; the backend that served each response is recorded in the run.",
    ]:
        story.append(Paragraph(f"• {line}", styles["body"]))
        story.append(Spacer(1, 2))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Authorized testing only. This report describes a security assessment of a system the operator "
        "declared they own or are permitted to test.", styles["small"]))

    doc.build(story)
    return buffer.getvalue()
