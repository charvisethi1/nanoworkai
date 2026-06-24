"""Interactive single-screen tool (calculator / converter / widget)."""
from __future__ import annotations

import json

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- Produce JSX that goes inside <script id="app-source" type="text/template">...</script> in the HTML wrapper.
- Declare `function App()` at the top level (not inside an IIFE, not as `const App = ...`).
- Declare any helper components as top-level `function` declarations BEFORE `App`.
- Use only React + ReactDOM + Tailwind utility classes (CDN in the wrapper). No imports. No requires. No external libraries.
- Use React.useState for state. No external state libraries.
- Reference brand color via Tailwind class `brand` or CSS var `var(--nw-brand)`.
- Reference hero via `window.HERO_IMAGE_URL` and logo via `window.LOGO_IMAGE_URL`. Treat as falsy when empty.
- Produce balanced braces. Do not emit a stray `}` or omit a closing `}`.
- Produce a complete, self-contained JSX block. No TODOs or partial sections.
- End with the final closing `}` for `function App()` and nothing after it except whitespace.
- After Babel transpile, the shell runs `if (typeof App === 'function') window.App = App;` — you MUST declare `function App()` at top level so `window.App = App` works.
"""


def build_prompt(ctx: dict) -> str:
    """Full prompt for tool-style single-screen previews."""
    inputs_json = json.dumps(ctx.get("inputs", []), indent=2)
    outputs_list = "\n".join(f"- {o}" for o in (ctx.get("outputs") or []))
    logic = ctx.get("logic", "")
    return f"""You are building a single-screen interactive TOOL preview as one React app.

TOOL CONTEXT:
- Name: {ctx.get('tool_name', '')}
- Description: {ctx.get('description', '')}
- Logic / formulas (plain English): {logic}

INPUTS — build a control for each (if empty, infer sensible defaults for this tool):
{inputs_json}

OUTPUTS — compute and display:
{outputs_list}

{_SHARED}

LAYOUT & BEHAVIOUR:
- THREE screens via React.useState routing:
  const [currentPage, setCurrentPage] = React.useState('tool');

SCREEN 1 — 'tool' (default):
- The interactive tool fills the screen as the hero experience
- Header: tool name left, nav buttons right: "How it works"
  (→ setCurrentPage('about')) and "Get this tool"
  (→ setCurrentPage('pricing'), styled as brand-colored button)
- Tool inputs are large, prominent, well-spaced
- Outputs update live on every input change
- Below outputs: earnings strip —
  "Turn this into a business"
  Interactive: "If [___] users pay [$___]/mo = $[calculated] revenue"
  Two number inputs bound to useState, calculation shown live
  CTA button "Build your version →" → setCurrentPage('pricing')

SCREEN 2 — 'pricing':
- Header with "← Back to tool" link
- Hero: "Own this tool. Keep the revenue."
- 3 pricing tiers (Free/Pro/Business), middle tier highlighted
- Monthly/annual toggle
- Each tier CTA: "Get started →"
- Revenue callout: "You keep [85]% of every payment"
- Footer note: "Built in 90 seconds by Nanowork AI"

SCREEN 3 — 'about':
- Header with "← Back to tool" link
- How it works (3 steps)
- Who it's for
- CTA → setCurrentPage('pricing')

REFERENCE EXAMPLE (pattern only; tailor to this tool):
- Mortgage calculator: inputs for loan amount, annual interest rate (%), term in years; output monthly payment plus a simple breakdown (principal vs interest feel). Guard divide-by-zero and empty inputs.

RULES:
- NO optional chaining (?.). NO nullish coalescing (??). Use `||` and explicit checks.
- NO imports/exports/markdown fences. React is global.
- Tailwind utilities only, no inline styles.
- CAMERA / MEDIA: `navigator.mediaDevices.getUserMedia(constraints)` without `?.`; only inside useEffect or handlers.

Output ONLY raw JSX/JavaScript starting with `function App()`."""
