# Spreadsheet template quality bar

A template is a working model someone downloads and uses the same day. The
validator (`scripts/validate_template.py`) enforces the floor; this file is
the full bar the generator should hit.

## Workbook structure

- Sheet 1: **Instructions**. What the template does, how to fill it in, which
  cells are inputs, one worked example description. No formulas needed here.
- Sheet 2+: the model. One concern per sheet (Inputs, Model, Dashboard is a
  good split for bigger templates; a single model sheet is fine for small
  calculators).
- Input cells visually distinct (light fill, e.g. FFF9E6) and grouped at the
  top or in a dedicated Inputs block. Everything downstream computes from
  them; a user should never edit a formula cell to use the template.
- Formulas everywhere a number derives from another number. A grid of typed
  constants is a table, not a template.
- Sample data prefilled so every formula shows a sensible result on open.
- Number formats set: currency cells as currency, percents as percents,
  dates as dates. Column widths sized to content.
- No external links, no macros, no volatile functions that break on
  LibreOffice/Google Sheets import (avoid OFFSET/INDIRECT where INDEX works).
- Freeze the header row on data-entry sheets.

## Metadata JSON (matches the site's template gallery schema)

`slug, title, category, shortDescription, about, link, order` required.
`about` is 2 to 4 sentences of HTML-free prose: what it does, who it is for,
what the inputs are. Same humanization rules as blogs: no em/en dashes, no
curly quotes, no filler. `link` points at the hosted file path
(`/template-files/<slug>.xlsx`) so the gallery's CTA downloads directly.

## Cover image

Never borrow another template's image; a wrong screenshot on the card erodes
trust in the whole gallery. Generate a real cover per template: render the
model sheet's header plus a few sample rows as a styled HTML table (yellow
input cells, computed columns, a totals row, a title bar naming the template)
and screenshot it headless at ~1200px wide, height fitted to content. Host it
with the site's static assets and point metadata `image` at it, `imageAlt` =
title.

## Naming

Slug mirrors the title, lowercase-hyphenated, ends with what it IS:
`-template`, `-calculator`, `-tracker`, `-forecast`, `-model`. Check the
existing gallery for collisions AND near-duplicates before proposing.
