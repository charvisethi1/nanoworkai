"""Fallback when taxonomy = other — flexible but rule-bound."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- Produce JSX inside <script id="app-source" type="text/template">...</script>.
- Declare `function App()` at the top level (not inside an IIFE, not `const App = ...`).
- Helper components as top-level `function` before `App`.
- React + ReactDOM + Tailwind utilities only (CDN). No imports/requires/external libraries.
- React.useState only for state.
- Brand: Tailwind `brand` or `var(--nw-brand)`.
- Images: `window.HERO_IMAGE_URL`, `window.LOGO_IMAGE_URL`; treat as falsy if empty.
- Balanced braces; complete JSX; no TODOs; end after `function App()` closes.
- The shell hoists with `if (typeof App === 'function') window.App = App;` — top-level `function App()` is required.
"""


def build_prompt(ctx: dict) -> str:
    return f"""The user's request did not fit cleanly into our standard build types. Build the simplest, most direct version of what they asked for.

CONTEXT:
- Name: {ctx.get('business_name') or ctx.get('tool_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Description lines: {ctx.get('problem', '')} | {ctx.get('solution', '')} | {ctx.get('description', '')}
- Audience: {ctx.get('audience', '')}
- Differentiator: {ctx.get('differentiator', '')}

Follow these constraints:
{_SHARED}

Default to a single-screen layout unless the request clearly needs more.

RULES:
- No `?.` / `??`. No imports/exports. Tailwind only.

Output ONLY raw JSX starting with `function App()`."""
