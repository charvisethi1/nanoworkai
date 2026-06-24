"""Lead capture / contact / RSVP / signup style forms."""
from __future__ import annotations

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- Produce JSX inside <script id="app-source" type="text/template">...</script>.
- Declare `function App()` at the top level. Helpers BEFORE `App`.
- React + Tailwind CDN only. No imports/requires/external libs. React.useState only.
- Brand: Tailwind `brand` class or `var(--nw-brand)`.
- Hero/logo: `window.HERO_IMAGE_URL`, `window.LOGO_IMAGE_URL` when relevant; treat empty as falsy.
- Balanced braces; complete JSX; end with closing `}` of `function App()` only.
- The runtime hoists with `if (typeof App === 'function') window.App = App;` after Babel — declare `function App()` at top level.
"""


def build_prompt(ctx: dict) -> str:
    return f"""You are building a FORM preview (lead capture / contact / RSVP / application) as a single React page.

BUSINESS / USE CASE CONTEXT:
- Business or product name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- What they do (problem/solution): {ctx.get('problem', '')} / {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}
- Differentiator: {ctx.get('differentiator', '')}

{_SHARED}

CONTENT:
- Header explaining what the form is for and what happens after submission.
- Form fields matching the user's described use case (infer sensible fields if needed).
- Client-side validation: required fields, basic email format, phone format where those fields exist.
- Submit handler: show an inline success state (this is a preview — no real backend).
- Success state MUST include this exact sentence (or very close): "This is a preview. To start receiving real responses, complete signup."
- useState for field values, errors, and submission success flag.

RULES:
- No `?.` or `??`. No imports/exports. Tailwind only.
- Balanced JSX; no TypeScript.

Output ONLY raw JSX starting with `function App()`."""
