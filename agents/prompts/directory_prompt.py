"""Browsable list / menu / catalog with optional filter."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- JSX for <script id="app-source" type="text/template">.</script>
- Top-level `function App()`; helpers before App.
- React + Tailwind CDN only; React.useState only; no imports.
- `brand` / `var(--nw-brand)`; `window.HERO_IMAGE_URL` / `window.LOGO_IMAGE_URL` when useful.
- Complete, balanced JSX; final line is closing `}` of `function App()`.
- After Babel: `if (typeof App === 'function') window.App = App;` — declare `function App()` at top level.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building a DIRECTORY / list preview (properties, menu items, team, catalog) as one React page.

CONTEXT:
- Name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Problem / solution: {ctx.get('problem', '')} — {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}

{_SHARED}

STRUCTURE:
- Hero or header introducing what is being listed.
- Grid or list of 6–12 sample items matching the domain (fake but realistic names and details).
- Each item: card with image placeholder area (gradient or Tailwind block), title, key metadata, "View" or "Contact" button.
- Optional: one text input filtering items by title (client-side filter via useState).
- Footer with brand and contact line.

RULES:
- No `?.` / `??`. No imports. Tailwind only.

Output ONLY raw JSX starting with `function App()`."""
