"""Appointment / reservation request UI."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- JSX inside <script id="app-source" type="text/template">.</script>
- Top-level `function App()` before any IIFE; helpers first.
- React + Tailwind CDN only; React.useState; no imports.
- Brand via `brand` / `var(--nw-brand)`; images via window globals when relevant.
- Balanced braces; complete file; `window.App = App` hoist requires top-level `function App()`.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building a BOOKING / reservation preview as one React page.

CONTEXT:
- Service / business: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- What they offer: {ctx.get('solution', '')}
- Who it's for: {ctx.get('audience', '')}

{_SHARED}

UI:
- Hero explaining what is being booked.
- Form: optional service selection (if multiple services make sense), date `<input type="date">`, choose one of 4–6 time-slot buttons (useState for selection), name + email.
- Submit shows confirmation state summarizing service/date/time.
- Footer with location or contact snippet.

RULES:
- No `?.` / `??`. Tailwind only; no imports.

Output ONLY raw JSX starting with `function App()`."""
