# TODO Blueprint (A4, 4 copies per page)

This repository contains printable daily planner templates for software + DevOps workflows:

- `todo-blueprint-a4.svg` -> A4 sheet with 4 identical TODO cards (manual fill)
- `generate_todo_pages.py` -> generates dated A4 pages with 4 cards per page

## How to print

1. Open `todo-blueprint-a4.svg` in any browser.
2. Print with:
   - Paper: **A4**
   - Scale: **100%** / **Actual size**
   - Margins: **None** (or minimal)
3. Cut the page into 4 cards.

## Design intent

Each card is optimized for simple daily execution:

- 10-line TODO list with checkboxes
- Compact work timeline with separate lanes:
  - Deep Work
  - Meetings
  - Horizontal time axis (7A to 9P) for quick cell shading
  - Core work hours (9A to 6P) subtly highlighted
- Blockers section
- Notes section
- Done % + carry-forward line
- Dotted center cut guides for easy 4-way cutting

Use one card per day and fill blocks directly with pen.

## Generate dated pages

Default behavior (generate 4 upcoming workday cards starting today, excluding weekends):

```bash
python3 generate_todo_pages.py
```

Generate N cards from today:

```bash
python3 generate_todo_pages.py --count 12
```

Generate cards from a future start date:

```bash
python3 generate_todo_pages.py --start-date 2026-04-15 --count 8
```

Generate by date range (inclusive):

```bash
python3 generate_todo_pages.py --start-date 2026-04-01 --end-date 2026-04-30
```

Include weekends:

```bash
python3 generate_todo_pages.py --start-date 2026-04-01 --end-date 2026-04-30 --include-weekends
```

Custom output folder:

```bash
python3 generate_todo_pages.py --count 20 --output-dir out/april-cards
```

Output files are written as:

- `generated/todo-page-001.svg`
- `generated/todo-page-002.svg`
- ... (4 dated cards per page)
