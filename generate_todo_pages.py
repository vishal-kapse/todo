#!/usr/bin/env python3
"""Generate dated TODO A4 pages (4 cards per page)."""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Layout:
    page_width: float = 210.0
    page_height: float = 297.0
    card_width: float = 94.0
    card_height: float = 137.5
    card_positions: tuple[tuple[float, float], ...] = (
        (8.0, 8.0),
        (108.0, 8.0),
        (8.0, 151.5),
        (108.0, 151.5),
    )


SVG_STYLE = """
      .title { font: 700 4.1px "Helvetica Neue", Arial, sans-serif; fill: #111827; letter-spacing: 0.15px; }
      .section { font: 700 2.7px "Helvetica Neue", Arial, sans-serif; fill: #1f2937; }
      .label { font: 500 2.35px "Helvetica Neue", Arial, sans-serif; fill: #374151; }
      .tiny { font: 500 2.0px "Helvetica Neue", Arial, sans-serif; fill: #6b7280; }
      .line { stroke: #9ca3af; stroke-width: 0.25; }
      .line-light { stroke: #d1d5db; stroke-width: 0.22; }
      .box { fill: #ffffff; stroke: #4b5563; stroke-width: 0.5; rx: 2.2; }
      .checkbox { fill: none; stroke: #6b7280; stroke-width: 0.25; rx: 0.4; }
      .workband { fill: #eef2f7; }
      .cutline { stroke: #9ca3af; stroke-width: 0.3; stroke-dasharray: 1.2 1.2; }
""".strip("\n")


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


def card_svg(x: float, y: float, dt: date | None, layout: Layout) -> str:
    date_text = dt.isoformat() if dt else ""
    day_text = dt.strftime("%a") if dt else ""

    # Escape text to keep SVG valid for all locales/inputs.
    date_text = html.escape(date_text)
    day_text = html.escape(day_text)

    lines = [
        f'  <g transform="translate({x},{y})">',
        f'    <rect class="box" x="0" y="0" width="{layout.card_width}" height="{layout.card_height}"/>',
        '    <text class="title" x="4.2" y="7">DAILY ENGINEERING TODO</text>',
        '    <text class="label" x="4.2" y="11.6">Date:</text>',
        '    <line class="line" x1="13.2" y1="11.2" x2="34" y2="11.2"/>',
        f'    <text class="label" x="13.6" y="10.9">{date_text}</text>',
        '    <text class="label" x="38" y="11.6">Day:</text>',
        '    <line class="line" x1="62" y1="11.2" x2="89.6" y2="11.2"/>',
        f'    <text class="label" x="46.0" y="10.9">{day_text}</text>',
        '    <text class="section" x="4.2" y="17">TODOS</text>',
    ]

    # TODO lines (11), slightly wider spacing for better writing.
    y_checkbox = 19.0
    y_line = 20.3
    for _ in range(11):
        lines.extend(
            [
                f'    <rect class="checkbox" x="4.2" y="{y_checkbox:.1f}" width="2.6" height="2.6"/>',
                f'    <line class="line" x1="8.2" y1="{y_line:.1f}" x2="89.6" y2="{y_line:.1f}"/>',
            ]
        )
        y_checkbox += 4.0
        y_line += 4.0

    lines.extend(
        [
            '    <text class="section" x="4.2" y="65.8">WORK TIMELINE</text>',
            '    <text class="tiny" x="5" y="78.5">Deep Work</text>',
            '    <text class="tiny" x="5" y="84.8">Meetings</text>',
            '    <line class="line" x1="4.2" y1="71.2" x2="89.6" y2="71.2"/>',
        ]
    )

    grid_x = 20.8
    grid_y = 74.4
    grid_w = 68.8
    grid_h = 12.4
    grid_bottom = grid_y + grid_h
    slot_w = grid_w / 15.0  # 7 AM -> 9 PM
    # Highlight core working hours: 9 AM to 6 PM.
    work_start_idx = 2  # 9 AM relative to 7 AM start
    work_hours = 9
    lines.append(
        f'    <rect class="workband" x="{grid_x + work_start_idx * slot_w:.2f}" y="{grid_y}" width="{work_hours * slot_w:.2f}" height="{grid_h}"/>'
    )
    lines.append(f'    <rect class="line-light" x="{grid_x}" y="{grid_y}" width="{grid_w}" height="{grid_h}" fill="none"/>')
    lines.append(f'    <line class="line-light" x1="{grid_x}" y1="{grid_y + (grid_h / 2):.2f}" x2="{grid_x + grid_w}" y2="{grid_y + (grid_h / 2):.2f}"/>')

    for idx in range(16):
        x_pos = grid_x + idx * slot_w
        lines.append(f'    <line class="line-light" x1="{x_pos:.2f}" y1="{grid_y:.2f}" x2="{x_pos:.2f}" y2="{grid_bottom:.2f}"/>')

    for hour in (7, 9, 11, 13, 15, 17, 19, 21):
        suffix = "A" if hour < 12 else "P"
        hour_12 = hour if 1 <= hour <= 12 else hour - 12
        label = f"{hour_12}{suffix}"
        idx = hour - 7
        label_x = grid_x + idx * slot_w - 1.2
        lines.append(f'    <text class="tiny" x="{label_x:.2f}" y="73.3">{label}</text>')

    lines.extend(
        [
            '    <text class="section" x="4.2" y="92.2">BLOCKERS</text>',
            '    <line class="line-light" x1="4.2" y1="94.2" x2="89.6" y2="94.2"/>',
            '    <line class="line-light" x1="4.2" y1="97.4" x2="89.6" y2="97.4"/>',
            '    <line class="line-light" x1="4.2" y1="100.6" x2="89.6" y2="100.6"/>',
            '    <line class="line-light" x1="4.2" y1="103.8" x2="89.6" y2="103.8"/>',
            '    <text class="section" x="4.2" y="108.4">NOTES</text>',
            '    <line class="line-light" x1="4.2" y1="110.4" x2="89.6" y2="110.4"/>',
            '    <line class="line-light" x1="4.2" y1="113.6" x2="89.6" y2="113.6"/>',
            '    <text class="label" x="4.2" y="134.3">Done %:</text>',
            '    <line class="line" x1="13.8" y1="134" x2="25" y2="134"/>',
            '    <text class="label" x="29" y="134.3">Carry Forward:</text>',
            '    <line class="line" x1="47.8" y1="134" x2="89.6" y2="134"/>',
            "  </g>",
        ]
    )

    return "\n".join(lines)


def page_svg(dates_for_page: list[date], layout: Layout) -> str:
    cards: list[str] = []
    for idx, (x, y) in enumerate(layout.card_positions):
        dt = dates_for_page[idx] if idx < len(dates_for_page) else None
        cards.append(card_svg(x, y, dt, layout))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">
  <style>
{SVG_STYLE}
  </style>
  <rect x="0" y="0" width="{layout.page_width}" height="{layout.page_height}" fill="#ffffff"/>
  <line class="cutline" x1="105" y1="0" x2="105" y2="297"/>
  <line class="cutline" x1="0" y1="148.5" x2="210" y2="148.5"/>
{chr(10).join(cards)}
</svg>
"""


def build_dates(args: argparse.Namespace) -> list[date]:
    if args.end_date:
        return iter_dates_by_range(args.start_date, args.end_date, args.include_weekends)
    return iter_dates_by_count(args.start_date, args.count, args.include_weekends)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate dated TODO A4 SVG pages (4 cards per page)."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=4,
        help="Number of cards/dates to generate (ignored when --end-date is provided). Default: 4",
    )
    parser.add_argument(
        "--start-date",
        type=parse_iso_date,
        default=date.today(),
        help="Start date in YYYY-MM-DD. Default: today",
    )
    parser.add_argument(
        "--end-date",
        type=parse_iso_date,
        default=None,
        help="Optional inclusive end date in YYYY-MM-DD",
    )
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Include Saturday and Sunday dates (default excludes weekends).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("generated"),
        help="Directory to write output SVG pages. Default: ./generated",
    )

    args = parser.parse_args()
    if args.count < 1:
        raise ValueError("--count must be >= 1")

    all_dates = build_dates(args)
    if not all_dates:
        raise ValueError("No dates selected. Check your date range/weekend settings.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    layout = Layout()

    page_count = 0
    for i in range(0, len(all_dates), 4):
        page_count += 1
        chunk = all_dates[i : i + 4]
        content = page_svg(chunk, layout)
        output_file = args.output_dir / f"todo-page-{page_count:03d}.svg"
        output_file.write_text(content, encoding="utf-8")

    print(
        f"Generated {page_count} page(s) in '{args.output_dir}' for {len(all_dates)} date(s)."
    )
    print(
        f"First date: {all_dates[0].isoformat()} | Last date: {all_dates[-1].isoformat()}"
    )


if __name__ == "__main__":
    main()
