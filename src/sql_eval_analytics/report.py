"""Render query results as human-readable text or JSON."""

from __future__ import annotations

import json


def _format_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        # The SQL already rounds; keep three decimals max, trim the rest.
        if value == int(value):
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def render_table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    columns = list(rows[0])
    cells = [[_format_value(row[c]) for c in columns] for row in rows]
    widths = [
        max(len(c), max(len(row[i]) for row in cells))
        for i, c in enumerate(columns)
    ]
    header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    rule = "-+-".join("-" * w for w in widths)
    lines = [header, rule]
    lines += [" | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in cells]
    return "\n".join(lines)


def render_text(results: dict[str, dict], questions: dict[str, str]) -> str:
    sections = []
    for name, result in results.items():
        sections.append(f"== {name} ==")
        sections.append(questions.get(name, ""))
        if "skipped" in result:
            sections.append(f"(skipped: {result['skipped']})")
        else:
            sections.append(render_table(result["rows"]))
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def render_json(results: dict[str, dict]) -> str:
    return json.dumps(results, indent=2, default=str) + "\n"
