"""Single informational document page."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- JSX for <script id="app-source" type="text/template">.</script>
- Top-level `function App()`; helpers before App.
- React + Tailwind CDN; React.useState if needed; no imports.
- `brand`, `var(--nw-brand)`; hero/logo globals when useful.
- Complete balanced JSX; closing `}` of `function App()` last.
- `if (typeof App === 'function') window.App = App;` after compile requires top-level `function App()`.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building an informational PAGE preview (FAQ, event details, policy, about-only) as one React component.

TOPIC / BUSINESS:
- Title / name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Core facts: {ctx.get('problem', '')} {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}

{_SHARED}

STRUCTURE:
- Clear header with topic.
- Body: multiple sections using h2 headings and paragraphs. Specific, plausible copy — no Lorem ipsum.
- If there are 4+ sections, add a simple table-of-contents list at the top linking via buttons that scroll (`id` on sections + simple onClick scroll or useState to expand sections).
- Footer with short brand attribution.

This is NOT a marketing landing hard-sell; stay informational and readable.

RULES:
- No `?.` / `??`. No imports. Tailwind only.

Output ONLY raw JSX starting with `function App()`."""
