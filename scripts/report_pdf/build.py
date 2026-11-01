"""Designed A4 PDF of the CascadeGuard technical report, rendered with Chromium (Playwright).

Every paragraph, bullet and table cell comes verbatim from docs/report/cascadeguard-report.md
(parsed with scripts/report_docx.py). The figures (KEY_FIGURES, TIMELINE, PIPELINE and the band
labels) only restate numbers and labels already in the text;
tests/integration/test_technical_report.py traces each one to the data and checks it is in the
committed PDF. The style sheet is style.css next to this file; the page uses the Inter font if
installed.

    uv run python scripts/report_pdf/build.py [--out PATH]

Writes docs/report/cascadeguard-report.pdf. Playwright and its Chromium are dev dependencies
(already used by the UI end-to-end test): `uv run playwright install chromium` once.
"""

import argparse
import html
import importlib.util
import re
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "docs" / "report" / "cascadeguard-report.md"
OUTPUT = ROOT / "docs" / "report" / "cascadeguard-report.pdf"

# ---------- figures (only labels and numbers already in the text) ----------

KEY_FIGURES = [
    ("4,812", "accounts locked by the health portal's AI fraud-risk model (T+15)"),
    ("3,950", "patients still locked out at T+60"),
    ("4", "coordination failures diagnosed in the baseline (candidate gaps)"),
    ("21", "clauses loaded: 19 reviewed, 2 illustrative, drafts never"),
    ("2 of 21", "ranked repairs meet every critical goal (scripted agents)"),
]

TIMELINE = [
    ("T+00", "Telecom AI deprioritises authentication SMS", "tel"),
    ("T+15", "Health AI locks 4,812 accounts", "hea"),
    ("T+30", "Each operator sees only its own side", "neu"),
    ("T+45", "Six roles must decide: report, share, authorise", "neu"),
    ("T+60", "3,950 patients still locked out", "hea"),
    ("T+75", "Window closes", "end"),
]

# The Y.3172 pipeline: (node, label, kind), and the three labels around it.
PIPELINE = [
    ("SRC", "injects & facts", "data"),
    ("C", "RoleView", "data"),
    ("PP", "boundary filter", "data"),
    ("M", "6 role agents", "agent"),
    ("P", "deterministic engine", "engine"),
    ("D", "apply & release", "engine"),
    ("SINK", "goals & failures", "out"),
]
MLFO_BAND = (
    "MLFO · deterministic orchestrator (not an agent) and repair search over the closed grammar"
)
SANDBOX_BAND = (
    "Sandbox · replay of the identical incident with a candidate repair, "
    "never applied to the baseline"
)
PROPOSAL_NOTE = "proposal only → accept or reject"
DASH = "\N{EN DASH}"  # the separator in the report title


def report_docx() -> Any:
    spec = importlib.util.spec_from_file_location(
        "report_docx", ROOT / "scripts" / "report_docx.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inline(text: str) -> str:
    out: list[str] = []
    for part in re.split(r"(\*\*.+?\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            out.append(f"<strong>{html.escape(part[2:-2])}</strong>")
        elif part.startswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def pill(cell: str) -> str:
    """Colour the outcome cells of the results table; the words stay as written."""
    c = inline(cell)
    if cell.startswith("met at"):
        return f'<span class="pill ok">{c}</span>'
    if cell == "unmet":
        return f'<span class="pill bad">{c}</span>'
    return c


def timeline_svg() -> str:
    w, h, x0, x1, y = 680, 92, 40, 640, 30
    step = (x1 - x0) / (len(TIMELINE) - 1)
    colours = {"tel": "#2b6cb0", "hea": "#c2410c", "neu": "#0f766e", "end": "#334155"}
    parts = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" class="fig">',
        f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#cbd5e1" stroke-width="2"/>',
    ]
    for i, (t, label, kind) in enumerate(TIMELINE):
        x = x0 + i * step
        col = colours[kind]
        parts.append(f'<circle cx="{x:.1f}" cy="{y}" r="6.5" fill="{col}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y - 13}" text-anchor="middle" class="t-time" '
            f'fill="{col}">{t}</text>'
        )
        lines: list[str] = []
        cur = ""
        for wd in label.split():
            if len(cur) + len(wd) + 1 > 19 and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = f"{cur} {wd}".strip()
        lines.append(cur)
        for j, ln in enumerate(lines):
            parts.append(
                f'<text x="{x:.1f}" y="{y + 22 + j * 11}" text-anchor="middle" '
                f'class="t-lab">{html.escape(ln)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def pipeline_svg() -> str:
    fill = {"data": "#e0f2fe", "agent": "#ede9fe", "engine": "#0f1b2d", "out": "#dcfce7"}
    ink = {"data": "#075985", "agent": "#5b21b6", "engine": "#ffffff", "out": "#166534"}
    width, bw, bh, gap, y = 680, 80, 46, 16, 44
    x0 = (width - (len(PIPELINE) * bw + (len(PIPELINE) - 1) * gap)) / 2
    p = [
        f'<svg viewBox="0 0 {width} 150" xmlns="http://www.w3.org/2000/svg" class="fig">',
        "<defs><marker id='ar' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='6' "
        "markerHeight='6' orient='auto'><path d='M0,0 L10,5 L0,10 z' fill='#64748b'/></marker>"
        "</defs>",
        # MLFO band
        f'<rect x="{x0}" y="6" width="{width - 2 * x0}" height="24" rx="5" fill="#f1f5f9" '
        'stroke="#cbd5e1"/>',
        f'<text x="{width / 2}" y="22" text-anchor="middle" class="p-band">{MLFO_BAND}</text>',
    ]
    centres: list[float] = []
    for i, (code, sub, kind) in enumerate(PIPELINE):
        x = x0 + i * (bw + gap)
        centres.append(x + bw / 2)
        p.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="6" fill="{fill[kind]}" '
            f'stroke="{ink[kind] if kind != "engine" else "#0f1b2d"}" stroke-opacity=".35"/>'
        )
        p.append(
            f'<text x="{x + bw / 2}" y="{y + 19}" text-anchor="middle" class="p-code" '
            f'fill="{ink[kind]}">{code}</text>'
        )
        p.append(
            f'<text x="{x + bw / 2}" y="{y + 34}" text-anchor="middle" class="p-sub" '
            f'fill="{ink[kind]}">{html.escape(sub)}</text>'
        )
        if i:
            p.append(
                f'<line x1="{x - gap + 1}" y1="{y + bh / 2}" x2="{x - 2}" y2="{y + bh / 2}" '
                f'stroke="#64748b" stroke-width="1.4" marker-end="url(#ar)"/>'
            )
    # proposal -> engine annotation
    p.append(
        f'<text x="{(centres[3] + centres[4]) / 2}" y="{y + bh + 13}" text-anchor="middle" '
        f'class="p-note">{PROPOSAL_NOTE}</text>'
    )
    # sandbox loop
    ys = 118
    p.append(
        f'<rect x="{x0}" y="{ys}" width="{width - 2 * x0}" height="24" rx="5" fill="#fff7ed" '
        'stroke="#fdba74"/>'
    )
    p.append(
        f'<text x="{width / 2}" y="{ys + 16}" text-anchor="middle" class="p-band" '
        f'fill="#9a3412">{SANDBOX_BAND}</text>'
    )
    p.append(
        f'<path d="M{centres[6]},{y + bh} V{ys}" stroke="#ea580c" stroke-width="1.3" '
        f'fill="none" stroke-dasharray="3 2" marker-end="url(#ar)"/>'
    )
    p.append(
        f'<path d="M{centres[0]},{ys} V{y + bh + 2}" stroke="#ea580c" stroke-width="1.3" '
        f'fill="none" stroke-dasharray="3 2" marker-end="url(#ar)"/>'
    )
    p.append("</svg>")
    return "".join(p)


# ---------- body ----------


def section_html(idx: int, sec: Any) -> str:
    out = [
        f'<section class="s{idx}"><h2><span class="num">{idx}</span>{html.escape(sec.title)}</h2>'
    ]
    blocks: list[tuple[str, Any]] = sec.blocks
    i = 0
    while i < len(blocks):
        kind, content = blocks[i]
        if kind == "bullet":
            items: list[str] = []
            while i < len(blocks) and blocks[i][0] == "bullet":
                items.append(blocks[i][1])
                i += 1
            cls = "req" if idx == 3 else "gaps" if idx == 6 else ""
            lis: list[str] = []
            for it in items:
                extra = ""
                if idx == 6:
                    extra = (
                        ' class="removed"' if "Removed at its cause" in it else ' class="masked"'
                    )
                lis.append(f"<li{extra}>{inline(it)}</li>")
            out.append(f'<ul class="{cls}">' + "".join(lis) + "</ul>")
            continue
        if kind == "table":
            rows: list[list[str]] = content
            tcls = "map" if idx == 4 else "results"
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body: list[str] = []
            for r in rows[1:]:
                cells: list[str] = []
                for j, c in enumerate(r):
                    if tcls == "results" and j in (1, 2):
                        cells.append(f"<td>{pill(c)}</td>")
                    elif tcls == "map" and j == 0:
                        cells.append(f'<td class="node">{inline(c)}</td>')
                    else:
                        cells.append(f"<td>{inline(c)}</td>")
                rcls = ' class="rep"' if r[0].startswith("Governed + rank-1") else ""
                body.append(f"<tr{rcls}>" + "".join(cells) + "</tr>")
            if idx == 4:
                out.append(f'<figure class="pipe">{pipeline_svg()}</figure>')
            out.append(
                f'<table class="{tcls}"><thead><tr>{head}</tr></thead>'
                f"<tbody>{''.join(body)}</tbody></table>"
            )
            i += 1
            continue
        text = str(content)
        cls = ""
        if text.startswith("**Controversy"):
            cls = "callout controversy"
        elif text.startswith("**Limits."):
            cls = "limits"
        elif idx == 5 and text.startswith("**"):
            cls = "run"
            if "rank-1 repair (scripted" in text:
                cls += " run-rep"
            elif text.startswith("**Ungoverned") or text.startswith("**Live"):
                cls += " run-warn"
        elif idx == 2 and text.startswith("**"):
            cls = "lead"
        out.append(f'<p class="{cls}">{inline(text)}</p>')
        if idx == 2 and i == 0:
            out.append(f'<figure class="tl">{timeline_svg()}</figure>')
        i += 1
    out.append("</section>")
    return "\n".join(out)


def build_html(markdown: str) -> str:
    report = report_docx().parse(markdown)
    pre, _, name = str(report.title).rpartition(DASH + " ")
    team: dict[str, str] = report.team
    kf = "".join(
        f'<div class="kf"><div class="kf-n">{html.escape(n)}</div>'
        f'<div class="kf-l">{html.escape(label)}</div></div>'
        for n, label in KEY_FIGURES
    )
    meta = "".join(
        f'<div class="m"><span class="mk">{html.escape(k)}</span> '
        f'<span class="mv">{html.escape(v)}</span></div>'
        for k, v in team.items()
    )
    sections = "\n".join(section_html(i + 1, s) for i, s in enumerate(report.sections))
    css = (HERE / "style.css").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>CascadeGuard Technical Report</title><style>{css}</style></head><body>
<header class="band">
  <div class="eyebrow">{html.escape(pre.strip())} {DASH}</div>
  <h1>{html.escape(name.strip())}</h1>
  <div class="meta">{meta}</div>
</header>
<div class="kfs">{kf}</div>
{sections}
</body></html>"""


FOOTER = (
    '<div style="width:100%;font-family:Inter;font-size:7.5px;color:#64748b;padding:0 16mm;'
    'display:flex;justify-content:space-between">'
    "<span>CascadeGuard · AI for Good Sandbox Hackathon · GM of AI</span>"
    '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


def render(page_html: str, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "report.html"
        source.write_text(page_html, encoding="utf-8")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(source.as_uri())
            page.wait_for_timeout(300)
            page.pdf(
                path=str(out),
                width="210mm",
                height="297mm",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=FOOTER,
                margin={"top": "13mm", "bottom": "14mm", "left": "15mm", "right": "15mm"},
            )
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    render(build_html(SOURCE.read_text(encoding="utf-8")), args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
