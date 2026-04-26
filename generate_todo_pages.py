#!/usr/bin/env python3
"""Generate dated A4 landscape pages: left A5 = full engineering todo template; right A5 = notes."""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from gcal_client import TIMELINE_SPAN_HOURS, TimelineSegment

# A4 landscape (mm)
PAGE_W = 297.0
PAGE_H = 210.0

PAGE_MARGIN = 5.0
CARD_GAP = 8.0

CARD_W = (PAGE_W - 2.0 * PAGE_MARGIN - CARD_GAP) / 2.0
CARD_H = PAGE_H - 2.0 * PAGE_MARGIN

_CARD_TOP = PAGE_MARGIN

DEFAULT_TODOS_FILE = Path("todos.txt")
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "TODO"

NUM_TODO_LINES = 11
OLD_TODO_LINE_STEP = 5.5

# Todo row text (must match .todo-row font-size in SVG_STYLE)
TODO_ROW_FONT_SIZE_PX = 3.525
TODO_TEXT_X = 8.5
CARD_INNER_RIGHT_INSET = 4.2
# Horizontal mm from text start to before line end; small pad avoids touching the margin
TODO_ROW_RIGHT_PAD_MM = 0.5
# Typical advance width / em for bold Latin sans (narrower than naive 1.0; wide glyphs rare in bulk)
TODO_ROW_AVG_CHAR_EM = 0.56

# Date/Day row (must match .meta-* font sizes in SVG_STYLE)
META_LABEL_FONT_PX = 3.0
META_VALUE_FONT_PX = 3.2
META_ROW_BASELINE = 12.05
META_LINE_Y = 12.48

# Todo checkboxes: rule y reference per row; text baseline sits above rule; checkbox centered on text
TODO_LINE_REF_START = 21.05
TODO_LINE_BASELINE_GAP = 0.55
TODO_CHECKBOX_H = 2.6
TODO_ROW_TEXT_CENTER_EM = 0.38
TODOS_SECTION_Y_REF = 17.6


@dataclass(frozen=True)
class Layout:
    page_width: float = PAGE_W
    page_height: float = PAGE_H
    card_width: float = CARD_W
    card_height: float = CARD_H
    card_positions: tuple[tuple[float, float], ...] = (
        (PAGE_MARGIN, _CARD_TOP),
        (PAGE_MARGIN + CARD_W + CARD_GAP, _CARD_TOP),
    )


SVG_STYLE = f"""
      .title {{ font: 700 4.1px "Helvetica Neue", Arial, sans-serif; fill: #111827; letter-spacing: 0.15px; }}
      .section {{ font: 700 2.7px "Helvetica Neue", Arial, sans-serif; fill: #1f2937; }}
      .label {{ font: 500 2.35px "Helvetica Neue", Arial, sans-serif; fill: #374151; }}
      .meta-label {{ font: 600 {META_LABEL_FONT_PX}px "Helvetica Neue", Arial, sans-serif; fill: #374151; }}
      .meta-value {{ font: 700 {META_VALUE_FONT_PX}px "Helvetica Neue", Arial, sans-serif; fill: #111827; }}
      .todo-row {{ font: 700 {TODO_ROW_FONT_SIZE_PX}px "Helvetica Neue", Arial, sans-serif; fill: #374151; }}
      .tiny {{ font: 500 2.0px "Helvetica Neue", Arial, sans-serif; fill: #6b7280; }}
      .line {{ stroke: #9ca3af; stroke-width: 0.25; }}
      .line-light {{ stroke: #d1d5db; stroke-width: 0.22; }}
      .box {{ fill: #ffffff; stroke: #4b5563; stroke-width: 0.5; rx: 2.2; }}
      .checkbox {{ fill: none; stroke: #6b7280; stroke-width: 0.25; rx: 0.4; }}
      .workband {{ fill: #eef2f7; }}
      .cutline {{ stroke: #9ca3af; stroke-width: 0.3; stroke-dasharray: 1.2 1.2; }}
      .cal-event {{ fill: #a5b4fc; stroke: #4f46e5; stroke-width: 0.12; rx: 0.35; opacity: 0.9; }}
      .cal-event-text {{ font: 600 1.4px "Helvetica Neue", Arial, sans-serif; fill: #1e1b4b; }}
""".strip("\n")


def timeline_calendar_svg(
    segments: list[TimelineSegment],
    grid_x: float,
    grid_w: float,
    grid_y: float,
    grid_h: float,
) -> list[str]:
    """Draw calendar blocks and short titles on the work timeline grid."""
    out: list[str] = []
    inset_y = 0.18
    pad_x = 0.1
    inner_h = max(grid_h - 2 * inset_y, 0.5)
    text_y = grid_y + grid_h / 2.0 + 0.5
    span = float(TIMELINE_SPAN_HOURS)
    for seg in segments:
        x0 = grid_x + (seg.start_h / span) * grid_w
        w = max((seg.end_h - seg.start_h) / span * grid_w, 0.35)
        x_draw = x0 + pad_x
        w_draw = max(w - 2 * pad_x, 0.2)
        out.append(
            f'    <rect class="cal-event" x="{x_draw:.2f}" y="{grid_y + inset_y:.2f}" '
            f'width="{w_draw:.2f}" height="{inner_h:.2f}"/>'
        )
        if w_draw >= 2.2:
            max_chars = max(4, min(36, int(w_draw / 0.34)))
            title = seg.title.strip() or "(event)"
            if len(title) > max_chars:
                title = title[: max_chars - 1] + "…"
            esc = html.escape(title)
            out.append(
                f'    <text class="cal-event-text" x="{x_draw + 0.12:.2f}" y="{text_y:.2f}">{esc}</text>'
            )
    return out


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: YYYY-MM-DD"
        ) from exc


def iter_dates_by_count(start: date, count: int, include_weekends: bool) -> list[date]:
    results: list[date] = []
    current = start
    while len(results) < count:
        if include_weekends or current.weekday() < 5:
            results.append(current)
        current += timedelta(days=1)
    return results


def iter_dates_by_range(start: date, end: date, include_weekends: bool) -> list[date]:
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")
    results: list[date] = []
    current = start
    while current <= end:
        if include_weekends or current.weekday() < 5:
            results.append(current)
        current += timedelta(days=1)
    return results


def _card_y(layout: Layout, y_ref: float) -> float:
    """Map reference y (mm) in 0–140 design to stretched coordinates; header y<17 unchanged."""
    if y_ref < 17:
        return y_ref
    return 17.0 + (y_ref - 17.0) * (layout.card_height - 4.0 - 17.0) / (134.0 - 17.0)


def todo_row_max_chars(layout: Layout) -> int:
    """Chars that fit between todo text x and inner_right at .todo-row size (viewBox mm)."""
    inner_right = layout.card_width - CARD_INNER_RIGHT_INSET
    usable_mm = inner_right - TODO_TEXT_X - TODO_ROW_RIGHT_PAD_MM
    if usable_mm <= 0:
        return 24
    per_char_mm = TODO_ROW_FONT_SIZE_PX * TODO_ROW_AVG_CHAR_EM
    n = int(usable_mm / per_char_mm)
    return max(24, min(n, 200))


def truncate_todo_row(text: str, max_chars: int) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def load_todo_sections(path: Path) -> list[list[str]]:
    """
    Load up to 11 todo lines per day.

    If the file contains a line that is exactly ``---``, the file is split into blocks (one per day).
    Empty blocks are skipped. With no ``---``, the first 11 non-comment lines apply to a single day.
    """
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    has_sep = any(line.strip() == "---" for line in lines)

    if not has_sep:
        day: list[str] = []
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if len(day) < NUM_TODO_LINES:
                day.append(s)
        return [day]

    chunks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.strip() == "---":
            chunks.append(cur)
            cur = []
        else:
            cur.append(line)
    chunks.append(cur)
    chunks = [c for c in chunks if any(l.strip() for l in c)]

    sections: list[list[str]] = []
    for chunk in chunks:
        day: list[str] = []
        for line in chunk:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if len(day) < NUM_TODO_LINES:
                day.append(s)
        sections.append(day)
    return sections


def todo_half_svg(
    x: float,
    y: float,
    dt: date | None,
    todo_items: list[str],
    layout: Layout,
    timeline_segments: list[TimelineSegment] | None = None,
) -> str:
    """Original full card: TODOS (11), WORK TIMELINE, BLOCKERS, NOTES, footer."""
    rows = (todo_items + [""] * NUM_TODO_LINES)[:NUM_TODO_LINES]

    date_text = dt.isoformat() if dt else ""
    day_text = dt.strftime("%a") if dt else ""
    date_text = html.escape(date_text)
    day_text = html.escape(day_text)

    cw = layout.card_width
    inner_right = cw - 4.2
    todo_max_chars = todo_row_max_chars(layout)

    date_line_x1 = 13.2
    date_line_x2 = round(min(56.0, cw * 0.40), 2)
    day_label_x = round(date_line_x2 + 2.8, 2)
    day_line_x1 = round(day_label_x + 8.2, 2)
    day_line_x2 = round(min(day_line_x1 + 18.0, inner_right - 1.0), 2)
    day_text_x = round(day_line_x1 + 0.4, 2)

    lines: list[str] = [
        f'  <g transform="translate({x},{y})">',
        f'    <rect class="box" x="0" y="0" width="{cw}" height="{layout.card_height}"/>',
        '    <text class="title" x="4.2" y="7">DAILY ENGINEERING TODO</text>',
        f'    <text class="meta-label" x="4.2" y="{META_ROW_BASELINE}">Date:</text>',
        f'    <line class="line" x1="{date_line_x1}" y1="{META_LINE_Y}" x2="{date_line_x2}" y2="{META_LINE_Y}"/>',
        f'    <text class="meta-value" x="13.6" y="{META_ROW_BASELINE}">{date_text}</text>',
        f'    <text class="meta-label" x="{day_label_x}" y="{META_ROW_BASELINE}">Day:</text>',
        f'    <line class="line" x1="{day_line_x1}" y1="{META_LINE_Y}" x2="{day_line_x2}" y2="{META_LINE_Y}"/>',
        f'    <text class="meta-value" x="{day_text_x}" y="{META_ROW_BASELINE}">{day_text}</text>',
        f'    <text class="section" x="4.2" y="{_card_y(layout, TODOS_SECTION_Y_REF):.2f}">TODOS</text>',
    ]

    for i in range(NUM_TODO_LINES):
        y_ln_ref = TODO_LINE_REF_START + i * OLD_TODO_LINE_STEP
        y_ln = _card_y(layout, y_ln_ref)
        y_tx = y_ln - TODO_LINE_BASELINE_GAP
        text_mid_y = y_tx - TODO_ROW_FONT_SIZE_PX * TODO_ROW_TEXT_CENTER_EM
        y_cb = text_mid_y - TODO_CHECKBOX_H / 2.0
        lines.extend(
            [
                f'    <rect class="checkbox" x="4.2" y="{y_cb:.2f}" width="{TODO_CHECKBOX_H}" height="{TODO_CHECKBOX_H}"/>',
                f'    <line class="line" x1="8.2" y1="{y_ln:.2f}" x2="{inner_right}" y2="{y_ln:.2f}"/>',
            ]
        )
        cell = rows[i].strip()
        if cell:
            esc = html.escape(truncate_todo_row(cell, todo_max_chars))
            lines.append(f'    <text class="todo-row" x="8.5" y="{y_tx:.2f}">{esc}</text>')

    last_todo_line_ref = TODO_LINE_REF_START + (NUM_TODO_LINES - 1) * OLD_TODO_LINE_STEP
    work_title_ref = last_todo_line_ref + 2.8
    sep_ref = work_title_ref + 3.5
    grid_y_ref = sep_ref + 4.0
    label_row_ref = grid_y_ref - 1.1

    work_title_y = _card_y(layout, work_title_ref)
    sep_y = _card_y(layout, sep_ref)
    grid_y = _card_y(layout, grid_y_ref)
    label_row_y = _card_y(layout, label_row_ref)

    lines.extend(
        [
            f'    <text class="section" x="4.2" y="{work_title_y:.2f}">WORK TIMELINE</text>',
            f'    <line class="line" x1="4.2" y1="{sep_y:.2f}" x2="{inner_right}" y2="{sep_y:.2f}"/>',
        ]
    )

    grid_x = 4.2
    grid_w = cw - 8.4
    grid_h = 6.8
    grid_bottom = grid_y + grid_h
    slot_w = grid_w / 15.0
    work_start_idx = 2
    work_hours = 9
    lines.append(
        f'    <rect class="workband" x="{grid_x + work_start_idx * slot_w:.2f}" y="{grid_y:.2f}" width="{work_hours * slot_w:.2f}" height="{grid_h}"/>'
    )
    lines.append(
        f'    <rect class="line-light" x="{grid_x}" y="{grid_y:.2f}" width="{grid_w}" height="{grid_h}" fill="none"/>'
    )

    for idx in range(16):
        x_pos = grid_x + idx * slot_w
        lines.append(
            f'    <line class="line-light" x1="{x_pos:.2f}" y1="{grid_y:.2f}" x2="{x_pos:.2f}" y2="{grid_bottom:.2f}"/>'
        )

    if timeline_segments:
        lines.extend(timeline_calendar_svg(timeline_segments, grid_x, grid_w, grid_y, grid_h))

    for hour in (7, 9, 11, 13, 15, 17, 19, 21):
        suffix = "A" if hour < 12 else "P"
        hour_12 = hour if 1 <= hour <= 12 else hour - 12
        label = f"{hour_12}{suffix}"
        idx = hour - 7
        label_x = grid_x + idx * slot_w - 1.2
        lines.append(f'    <text class="tiny" x="{label_x:.2f}" y="{label_row_y:.2f}">{label}</text>')

    grid_bottom_ref = grid_y_ref + 6.8
    blockers_y_ref = grid_bottom_ref + 3.4
    blockers_y = _card_y(layout, blockers_y_ref)

    lines.extend(
        [
            f'    <text class="section" x="4.2" y="{blockers_y:.2f}">BLOCKERS</text>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 2.0):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 2.0):.2f}"/>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 5.2):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 5.2):.2f}"/>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 8.4):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 8.4):.2f}"/>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 11.6):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 11.6):.2f}"/>',
            f'    <text class="section" x="4.2" y="{_card_y(layout, blockers_y_ref + 16.2):.2f}">NOTES</text>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 18.2):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 18.2):.2f}"/>',
            f'    <line class="line-light" x1="4.2" y1="{_card_y(layout, blockers_y_ref + 21.4):.2f}" x2="{inner_right}" y2="{_card_y(layout, blockers_y_ref + 21.4):.2f}"/>',
            f'    <text class="label" x="4.2" y="{_card_y(layout, 134.3):.2f}">Done %:</text>',
            f'    <line class="line" x1="13.8" y1="{_card_y(layout, 134.0):.2f}" x2="25" y2="{_card_y(layout, 134.0):.2f}"/>',
            f'    <text class="label" x="29" y="{_card_y(layout, 134.3):.2f}">Carry Forward:</text>',
            f'    <line class="line" x1="47.8" y1="{_card_y(layout, 134.0):.2f}" x2="{inner_right}" y2="{_card_y(layout, 134.0):.2f}"/>',
            "  </g>",
        ]
    )

    return "\n".join(lines)


def notes_half_svg(x: float, y: float, dt: date | None, layout: Layout) -> str:
    cw = layout.card_width
    inner_right = cw - 4.2
    sub = ""
    if dt:
        sub = html.escape(f"{dt.strftime('%A')} — {dt.isoformat()}")
    lines: list[str] = [
        f'  <g transform="translate({x},{y})">',
        f'    <rect class="box" x="0" y="0" width="{cw}" height="{layout.card_height}"/>',
        '    <text class="title" x="4.2" y="7">NOTES</text>',
        f'    <text class="tiny" x="4.2" y="11.4">{sub}</text>',
        '    <text class="section" x="4.2" y="17">TODAY</text>',
    ]
    y_ref = 21.0
    while y_ref < 132.0:
        yy = _card_y(layout, y_ref)
        lines.append(
            f'    <line class="line-light" x1="4.2" y1="{yy:.2f}" x2="{inner_right}" y2="{yy:.2f}"/>'
        )
        y_ref += 5.4

    lines.append("  </g>")
    return "\n".join(lines)


def page_svg(
    dt: date,
    todo_items: list[str],
    layout: Layout,
    timeline_segments: list[TimelineSegment] | None = None,
) -> str:
    (lx, ly), (rx, ry) = layout.card_positions
    left = todo_half_svg(lx, ly, dt, todo_items, layout, timeline_segments)
    right = notes_half_svg(rx, ry, dt, layout)
    cut_x = PAGE_MARGIN + layout.card_width + CARD_GAP / 2.0

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{layout.page_width}mm" height="{layout.page_height}mm" viewBox="0 0 {layout.page_width} {layout.page_height}">
  <style>
{SVG_STYLE}
  </style>
  <rect x="0" y="0" width="{layout.page_width}" height="{layout.page_height}" fill="#ffffff"/>
  <line class="cutline" x1="{cut_x}" y1="0" x2="{cut_x}" y2="{layout.page_height}"/>
{left}
{right}
</svg>
"""


def build_dates(args: argparse.Namespace) -> list[date]:
    if args.end_date:
        return iter_dates_by_range(args.start_date, args.end_date, args.include_weekends)
    return iter_dates_by_count(args.start_date, args.count, args.include_weekends)


def pdf_converter_name() -> str | None:
    if shutil.which("rsvg-convert"):
        return "rsvg-convert"
    if shutil.which("inkscape"):
        return "inkscape"
    return None


def convert_svg_to_pdf(svg: Path, pdf: Path) -> None:
    """Write *pdf* from *svg* using rsvg-convert (librsvg) or Inkscape."""
    if shutil.which("rsvg-convert"):
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)],
            check=True,
        )
        return
    if shutil.which("inkscape"):
        subprocess.run(
            [
                "inkscape",
                str(svg),
                f"--export-filename={pdf}",
                "--export-type=pdf",
            ],
            check=True,
        )
        return
    raise RuntimeError("No supported SVG→PDF tool found (rsvg-convert or inkscape).")


def main() -> None:
    tomorrow = date.today() + timedelta(days=1)
    parser = argparse.ArgumentParser(
        description="Generate A4 landscape: left A5 = full daily engineering todo (from todos.txt); "
        "right A5 = notes. Default start date: tomorrow."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of dated pages (ignored when --end-date is set). Default: 1",
    )
    parser.add_argument(
        "--start-date",
        type=parse_iso_date,
        default=None,
        help="First page date (YYYY-MM-DD). Default: tomorrow",
    )
    parser.add_argument(
        "--end-date",
        type=parse_iso_date,
        default=None,
        help="Inclusive end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Include Saturday and Sunday (default: weekdays only).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for SVG (and PDF with --pdf). Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--todos-file",
        type=Path,
        default=DEFAULT_TODOS_FILE,
        help=f"Todo list file. Default: {DEFAULT_TODOS_FILE}",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="After writing SVGs, also write a .pdf next to each file (needs rsvg-convert or inkscape).",
    )
    parser.add_argument(
        "--google-calendar",
        action="store_true",
        help="Fill WORK TIMELINE from Google Calendar (requires pip install -r requirements-google.txt and OAuth setup; see gcal_client.py).",
    )
    parser.add_argument(
        "--gcal-credentials-dir",
        type=Path,
        default=Path.home() / ".config" / "todo-gcal",
        help="Directory with client_secret.json and token.json. Default: ~/.config/todo-gcal/",
    )
    parser.add_argument(
        "--gcal-calendar-id",
        default="primary",
        help="Calendar ID: 'primary' or e.g. workspace email / calendar address from Calendar settings.",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        metavar="IANA",
        help="Timezone for day boundaries (e.g. America/New_York). Default: system local offset.",
    )

    args = parser.parse_args()
    if args.start_date is None:
        args.start_date = tomorrow
    if args.count < 1:
        raise ValueError("--count must be >= 1")

    all_dates = build_dates(args)
    if not all_dates:
        raise ValueError("No dates selected. Check range/weekend settings.")

    sections = load_todo_sections(args.todos_file)
    if not sections and not args.todos_file.exists():
        print(
            f"Warning: todos file '{args.todos_file}' not found; all todo rows will be blank.",
            file=sys.stderr,
        )
    # Pad section list so each generated day has a list (possibly empty)
    while len(sections) < len(all_dates):
        sections.append([])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    layout = Layout()

    calendar_events: list | None = None
    gcal_tz = None
    segments_for_print_day = None
    if args.google_calendar:
        try:
            from gcal_client import (
                fetch_events_range,
                resolve_timezone,
                segments_for_print_day as _segments_for_print_day,
            )

            segments_for_print_day = _segments_for_print_day
        except ImportError as exc:
            print(
                "Google Calendar requires extra packages. Run:\n"
                "  pip install -r requirements-google.txt",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        try:
            gcal_tz = resolve_timezone(args.timezone)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(1) from exc
        calendar_events = fetch_events_range(
            all_dates[0],
            all_dates[-1],
            args.gcal_calendar_id,
            args.gcal_credentials_dir,
            gcal_tz,
        )
        print(
            f"Loaded {len(calendar_events)} calendar event(s) "
            f"for {all_dates[0].isoformat()} … {all_dates[-1].isoformat()} (tz: {gcal_tz!s}).",
            file=sys.stderr,
        )

    written_svg: list[Path] = []
    for i, dt in enumerate(all_dates):
        todo_items = sections[i] if i < len(sections) else []
        segments: list[TimelineSegment] | None = None
        if calendar_events is not None and gcal_tz is not None and segments_for_print_day:
            segments = segments_for_print_day(calendar_events, dt, gcal_tz)
        content = page_svg(dt, todo_items, layout, segments)
        out = args.output_dir / f"todo-page-{dt.isoformat()}.svg"
        out.write_text(content, encoding="utf-8")
        written_svg.append(out)

    print(f"Generated {len(all_dates)} page(s) in '{args.output_dir}'.")
    print(f"First: {all_dates[0].isoformat()} | Last: {all_dates[-1].isoformat()}")

    if args.pdf:
        tool = pdf_converter_name()
        if tool is None:
            print(
                "PDF export requested but neither 'rsvg-convert' nor 'inkscape' was found. "
                "Install e.g.: brew install librsvg",
                file=sys.stderr,
            )
            sys.exit(1)
        for svg in written_svg:
            pdf = svg.with_suffix(".pdf")
            convert_svg_to_pdf(svg, pdf)
        print(
            f"Wrote {len(written_svg)} PDF file(s) next to the SVGs (using {tool})."
        )


if __name__ == "__main__":
    main()
