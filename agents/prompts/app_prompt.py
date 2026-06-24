"""Multi-screen SaaS-style demo (single file, conditional screens)."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- JSX for <script id="app-source" type="text/template">.</script>
- Top-level `function App()`; helper screens as top-level `function` declarations BEFORE `App`.
- React + Tailwind CDN only; React.useState for screen state and data; NO React Router, NO `Routes`, no imports.
- `brand`, `var(--nw-brand)`; `window.HERO_IMAGE_URL`, `window.LOGO_IMAGE_URL` if needed.
- Balanced braces; one file only; end with `function App()` closing `}`.
- Babel then runs `if (typeof App === 'function') window.App = App;` — you MUST use top-level `function App()`.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building a multi-screen APP preview (SaaS-style demo) in ONE React file.

PRODUCT:
- Name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Problem / solution: {ctx.get('problem', '')} — {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}

{_SHARED}

COMPLEXITY WARNING — be conservative:
- Fewer screens beats broken code. Prefer 3–4 screens max.
- Simple inline sample data; no backend; no imports.
- Track active screen with `React.useState` (e.g. 'dashboard'); sidebar OR top nav with 3–5 labels switching that state.
- Include at least one dashboard-style screen with summary cards / stats, and 1–2 simpler list or detail screens with fake rows.
- Conditional rendering only — no router library.

RULES:
- No `?.` / `??`. No imports/exports. Tailwind only.

Output ONLY raw JSX starting with helper functions then `function App()`."""
