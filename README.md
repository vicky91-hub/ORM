# Sumadhura ORM Performance Dashboard

## What this is
A single-page, self-contained ORM (Online Reputation Management) dashboard for Sumadhura,
covering Social, GMB, Reddit, and Quora. Built as one HTML file — no build step, no bundler,
no npm dependencies. All data is currently hardcoded as JS objects/arrays inside the file
(pulled from Google Sheets by Claude in the original build session, not live-connected).

## Files
- **`index.html`** — the entire dashboard. HTML, CSS, and JS all in one file. The only
  external dependency is Chart.js, loaded via CDN (`<script src="https://cdnjs.cloudflare.com/...">`)
  — you'll need an internet connection for the charts to render; everything else works offline.
- **`docs/ORM_Dashboard_Specs.md`** — the most important file to read first. This is the running
  build log: every revision, why each decision was made, data sources and their exact column
  mappings, known data-quality caveats, bugs that were fixed (and why, so they don't get
  reintroduced), and the exact patterns used for repeated UI elements (theme tables, switchable
  bar charts, sticky header, etc). If you're picking this up cold, start here.
- **`docs/NSD_Brand_Guidelines.md`** — North Star Digital's brand guide (colors, typography,
  logo rules) that this dashboard's styling follows.

## Opening this in VS Code
1. Unzip/copy this folder anywhere on your machine.
2. `File > Open Folder...` and select this folder (or `code .` from a terminal in this folder,
   if the `code` CLI command is installed).
3. That's it — no `npm install`, no build step. Open `index.html` directly.

### Previewing it
- Simplest: right-click `index.html` in the VS Code file explorer → **"Reveal in Finder/Explorer"**
  → double-click to open in your browser. Or just drag `index.html` into any browser window.
- Nicer: install the **Live Server** extension (Ritwick Dey) in VS Code, then right-click
  `index.html` → **"Open with Live Server"**. This gives you auto-refresh on save, which is much
  faster for iterating on layout/styling.

### Editing
Everything is in `index.html`:
- `<style>` block at the top — all CSS, organized roughly in the order things appear on the page.
- `<body>` — the markup. Sections are commented (`<!-- REDDIT -->`, `<!-- GMB -->`, etc.).
- `<script>` block at the bottom — all the data (as plain JS objects/arrays near the top of the
  script) and rendering logic. Search for `// ----------` comments to jump between sections —
  the file is organized into labeled blocks (DATA, RENDER: ..., CHARTS, TAB FILTER, etc).

If you want VS Code to properly color/format the embedded CSS and JS inside the HTML file,
the built-in HTML language support already does this — no extra extension needed, though
**ESLint**/**Prettier** extensions can help if you want linting/auto-formatting on the JS specifically.

## A note on "live" data
This dashboard does **not** poll Google Sheets or any API. Every number is a snapshot baked in
at generation time by Claude reading the underlying Google Sheets directly. To refresh the data,
the underlying sheets need to be re-read and the JS data objects in `index.html` updated by hand
(or by asking Claude to do it again) — see the "How frequently will this auto-fetch" discussion
in `docs/ORM_Dashboard_Specs.md` if you want to explore making this genuinely live (the short
version: a static HTML file can't safely do this on its own; Looker Studio connected directly to
the Sheets, or a small backend proxy, are the realistic paths there).

## Continuing to iterate with Claude, from VS Code
If you want to keep having Claude make changes to this dashboard (rather than hand-editing),
**Claude Code** can be installed as a VS Code extension and pointed at this folder — it can read
`docs/ORM_Dashboard_Specs.md` for context and edit `index.html` directly in your local repo,
so changes land straight in your working copy instead of round-tripping through chat uploads.
