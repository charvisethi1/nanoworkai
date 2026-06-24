"""Creative / freelancer portfolio."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- JSX for <script id="app-source" type="text/template">.</script>
- Top-level `function App()`; helpers before App.
- React + Tailwind CDN; React.useState; no imports.
- `brand`, `var(--nw-brand)`, `window.HERO_IMAGE_URL`, `window.LOGO_IMAGE_URL` as needed.
- Complete balanced JSX; end with `function App()` closing brace.
- Shell hoists via `if (typeof App === 'function') window.App = App;` — top-level `function App()` required.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building a PORTFOLIO preview as a single restrained, tasteful React page.

SUBJECT:
- Name / studio: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Focus: {ctx.get('problem', '')} {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}

{_SHARED}

SECTIONS:
- Hero with creator name, tagline, primary CTA.
- Grid of 6–9 work samples: image placeholder, title, year, short description (domain-specific sample data).
- About section.
- Contact section (simple form or contact details).
- Design: portfolios foreground the work — minimal chrome, generous whitespace, no noisy marketing gimmicks.

RULES:
- No `?.` / `??`. No imports. Tailwind only.

Output ONLY raw JSX starting with `function App()`."""
