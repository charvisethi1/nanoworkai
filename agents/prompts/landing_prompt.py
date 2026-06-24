"""Marketing / product-app landing-style preview prompt (moved from page_builder_agent)."""
from __future__ import annotations

from ...orchestration.build_modes import PRODUCT_APP, resolve_site_mode

SYSTEM_PROMPT = """You are an elite UI/UX designer and frontend engineer.
Every product you build has a completely unique visual identity. You make
bold, specific design choices:

- Use the brand color as a starting point, then build a full palette around it
- Pick typography that matches the product personality
- Vary layouts — asymmetric, editorial, grid, cinematic — whatever fits
- Add micro-interactions and CSS transitions that feel native to the product
- Write copy that sounds like it came from the actual company
- A social app should feel social. A dev tool should feel technical.
  A luxury brand should feel premium.

You NEVER produce generic SaaS templates. Same structure, wildly different
aesthetic every time.

The shell exposes these Tailwind color utilities:
- bg-brand, text-brand, border-brand (primary brand color)
- bg-brand-light (10% opacity tint)
- bg-brand-mid (50% opacity)

For section variety use:
- Alternating bg-white and bg-zinc-50 sections for light styles
- Alternating bg-zinc-950 and bg-zinc-900 sections for dark styles
- bg-brand for ONE bold accent section
- Use opacity variants: bg-brand/10, bg-brand/20 for subtle tints

This gives you 5+ distinct background options per page."""

_SHARED = """
SHARED JSX ARCHITECTURE (mandatory):
- Produce JSX that goes inside <script id="app-source" type="text/template">...</script> in the HTML wrapper.
- Declare `function App()` at the top level (not inside an IIFE, not as `const App = ...`).
- Declare any helper components (Nav, Footer, screen components, etc.) as top-level `function` declarations BEFORE `App`.
- Use only React + ReactDOM + Tailwind utility classes (CDN in the wrapper). No imports. No requires. No external libraries.
- Use React.useState for state. No external state libraries.
- Reference brand color via Tailwind class `brand` (wrapper Tailwind config) or CSS var `var(--nw-brand)`.
- Reference hero image via `window.HERO_IMAGE_URL` and logo via `window.LOGO_IMAGE_URL`. Treat as falsy when empty.
- Produce balanced braces. Do not emit a stray `}` or omit a closing `}`.
- Produce a complete, self-contained JSX block. No TODOs or partial sections.
- End with the final closing `}` for `function App()` and nothing after it except whitespace.
- The bootstrap transpiles your functions with Babel, then hoists the root with:
  `if (typeof App === 'function') window.App = App;`
  You MUST declare `function App()` at the top level so `window.App = App` succeeds.

NAVBAR AND FOOTER (critical — design these from scratch):
- Generate a complete page including a custom navbar and footer.
- The navbar and footer MUST be unique to this product — design them to match
  the product's visual identity, tone, and audience.
- Do NOT use generic SaaS nav patterns (center logo + links + auth buttons).
- Consider: asymmetric layouts, unconventional positioning, custom brand marks,
  navigation patterns that fit the product type (dashboard nav for tools,
  minimal nav for portfolios, bold nav for gaming, etc.).
- The navbar should feel like it was custom-designed for THIS product, not
  templated from a component library.
"""


def _product(ctx: dict, design_brief: str, features_text: str, hero: str, logo: str, rag_injection: str = "") -> str:
    return f"""You are building a FULLY FUNCTIONING interactive preview of a real product, as a single React SPA.

PRODUCT CONTEXT:
- Name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Problem: {ctx.get('problem', '')}
- Solution: {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}
- Features: {features_text}
- Differentiator: {ctx.get('differentiator', '')}

{design_brief}

BRAND IMAGERY (Nano Banana Pro):
{hero}

{logo}

{rag_injection}

{_SHARED}

CRITICAL RULE: This is NOT a marketing waitlist page. The visitor should EXPERIENCE the actual
product first, then — only at the very end — see a landing/conversion moment.
Do NOT include any "Join waitlist" email captures anywhere except on the final Landing screen.

ARCHITECTURE — a single React SPA with `React.useState`-based routing:
  const [currentPage, setCurrentPage] = React.useState('app');
  const [authed, setAuthed] = React.useState(false);

SCREENS (all rendered by `App`, switched via setCurrentPage):

1. 'app' — THE PRODUCT EXPERIENCE. This is the DEFAULT screen the visitor lands on.
   Build a working, interactive product UI specifically tailored to this business:
     • If it's a SaaS/dashboard product: a realistic dashboard with KPI cards,
       charts (as styled div grids or progress bars), a searchable/filterable
       table of example rows, and at least one working action button that
       toggles state (e.g. add item, change status). Populate with realistic
       made-up data — 6-10 example rows minimum, named specifically to this
       industry (not "User 1" / "Item A"). No Lorem ipsum.
     • If it's a marketplace/directory: a browseable grid of 6-8 example
       listings with category filters and a working search input bound to
       React state. Each listing has a unique name and realistic details.
     • If it's a consumer app: the primary interaction flow working end-to-end
       (e.g. input → output, swipe → match, add → list). At least one
       React.useState hook driving the core behaviour.
     • If it's content/media: a feed or gallery of 6+ example items with
       working hover / expand / like interactions.
   Include a small top header inside this screen with the product name on the
   left and these nav buttons on the right: "Pricing" (→ setCurrentPage('pricing')),
   "Log in" (→ setCurrentPage('login')), "Sign up" (→ setCurrentPage('signup')).
   At the BOTTOM of the product experience, add a conversion band with a
   headline like "Make {ctx.get('business_name', 'this')} yours." and a primary
   CTA button "Get started →" that calls setCurrentPage('landing'). This is the
   only place the user gets nudged toward the landing page from within the app.

2. 'login' — a working login screen. Email + password fields bound to React.useState,
   a submit button that flips a `submitted` state and shows a success panel,
   "Forgot password?" text link, and a "Need an account? Sign up" link that
   calls setCurrentPage('signup'). Top-left "← Back to app" link calling
   setCurrentPage('app').

3. 'signup' — a working signup screen. Name + email + password fields bound to
   React.useState, a terms checkbox, submit button that flips a `submitted`
   state and shows a warm success panel, and a link "Have an account? Log in"
   to setCurrentPage('login'). Top-left "← Back to app" link calling
   setCurrentPage('app').

4. 'pricing' — 3 pricing tiers tailored to this product. Middle tier highlighted
   as "Most popular". Every tier's CTA button calls setCurrentPage('signup').
   Include a monthly/annual toggle bound to React.useState that changes the
   displayed prices by ~20% (annual discount). Top-left "← Back to app" link.

5. 'landing' — THE FINAL CONVERSION MOMENT. This is the marketing landing page,
   but it's the LAST thing the user sees, not the first. Include:
     • Hero with the tagline, a one-liner value prop, and a primary CTA
       "Create your account" that calls setCurrentPage('signup').
     • A 3-card features grid (use ctx features above, one specific benefit per card).
     • A secondary CTA band at the bottom that also calls setCurrentPage('signup').
   A "← Back to the app" link at the very top returns to setCurrentPage('app').

SECTION GOALS (product_app): hero experience via default 'app' screen, problem/solution felt in copy, features, social proof where natural, FAQ if it fits a screen, strong CTA on landing screen, footer content integrated where appropriate.

VISUAL IDENTITY (make strong choices here):
- Build a full color palette: primary (brand), secondary, accent, background,
  surface, and text colors — not just one brand color on white
- Choose a font pairing from Google Fonts that matches the product personality
- Pick a layout personality: editorial, minimal, bold, corporate, playful,
  technical, luxury — and commit to it fully
- Use varied section backgrounds (not all white), gradients, patterns,
  or textures where appropriate
- Make the navbar and footer feel custom-built for this product, not generic

RULES (follow exactly — violations break Babel standalone):
- Define the screen components as separate functions (AppScreen, LoginScreen,
  SignupScreen, PricingScreen, LandingScreen) BEFORE the final `App` function.
- `App` is the LAST function. It sets up currentPage state, passes setCurrentPage
  to each screen, and renders exactly one screen via conditional JSX.
- NO optional chaining (?.). NO nullish coalescing (??). Use `||` and explicit checks.
- NO imports, NO exports, NO markdown fences. React is a global.
- Close every JSX tag. No self-closing divs. No TypeScript.
- All content specific to this product. No Lorem ipsum, no generic filler.
- Use Tailwind utility classes only, no inline styles.
- CAMERA / MEDIA ACCESS: call `navigator.mediaDevices.getUserMedia(constraints)`
  directly — never chain `?.` on navigator, mediaDevices, or getUserMedia.
  Use `.then(fn).catch(fn)` chains or a try/catch inside a regular helper function.
  Never put camera/media logic directly in a React component body — always inside
  React.useEffect or a button onClick handler. Every {{ and }} MUST be balanced.

UNIQUENESS REQUIREMENT:
This site must look completely different from a generic SaaS template.
Specific requirements:
- Use the brand_color as a starting point but build a FULL palette around it
- The hero section layout must match hero_layout exactly — do not default to centered
- Section backgrounds must vary — not all white or all dark
- At least one section must use a gradient, pattern, or bold background color
- Typography sizes must be dramatic where appropriate — don't play it safe
- Interactive elements must have hover states that feel intentional
- The overall aesthetic must be immediately recognizable as {ctx.get('design_style', 'minimal')}

If someone looked at this site and could mistake it for any other site,
you have failed. Make it unmistakably this product.

Output ONLY the raw JavaScript/JSX starting with the first function definition."""


def _marketing(ctx: dict, design_brief: str, features_text: str, hero: str, logo: str, rag_injection: str = "") -> str:
    return f"""You are building a polished startup WEBSITE preview as a single React page.

PRODUCT CONTEXT:
- Name: {ctx.get('business_name', '')}
- Tagline: {ctx.get('tagline', '')}
- Problem: {ctx.get('problem', '')}
- Solution: {ctx.get('solution', '')}
- Audience: {ctx.get('audience', '')}
- Features: {features_text}
- Differentiator: {ctx.get('differentiator', '')}

{design_brief}

BRAND IMAGERY (Nano Banana Pro):
{hero}

{logo}

{rag_injection}

{_SHARED}

GOAL:
- Build a website / landing experience because that is what this business needs.
- Do NOT turn this into a logged-in dashboard, internal admin, analytics console,
  portal shell, or fake product infrastructure unless the context explicitly asks for one.
- The default experience should feel like a real public-facing website someone could ship today.

REQUIRED SECTIONS:
1. Hero — strong headline, one-line value proposition, primary CTA and secondary CTA.
2. Social proof or trust bar — logos, metrics, testimonials, or credibility markers.
3. Problem / solution section — make the pain and the transformation obvious.
4. Features section — 3 concrete, audience-specific feature/benefit cards.
5. How it works or workflow section — 3 clear steps or stages.
6. Audience/use-cases section or differentiator section.
7. FAQ section (accordion or tabbed) when it fits the business.
8. Final CTA band plus a simple footer area.

INTERACTION REQUIREMENTS:
- Use React.useState for at least one tasteful interaction that suits a website:
  tabs, FAQ accordion, pricing toggle, testimonial switcher, before/after switch,
  use-case filters, or feature spotlight. This is a website, not a dead mock.
- The page should still read as a website first, not a product dashboard.

VISUAL IDENTITY (make strong choices here):
- Build a full color palette: primary (brand), secondary, accent, background,
  surface, and text colors — not just one brand color on white
- Choose a font pairing from Google Fonts that matches the product personality
- Pick a layout personality: editorial, minimal, bold, corporate, playful,
  technical, luxury — and commit to it fully
- Use varied section backgrounds (not all white), gradients, patterns,
  or textures where appropriate
- Make the navbar and footer feel custom-built for this product, not generic

COPY + DESIGN RULES:
- All copy must be specific to this business. No Lorem ipsum. No generic placeholders.
- No "Join waitlist" framing unless the business context explicitly implies pre-launch hype.
- No login, signup, pricing, dashboard, KPI table, or fake admin shell unless the context explicitly needs it.
- Use Tailwind utility classes only. No inline styles.
- NO optional chaining (?.). NO nullish coalescing (??). Use `||` and explicit checks.
- NO imports, NO exports, NO markdown fences. React is a global.
- Close every JSX tag. No self-closing divs. No TypeScript.

TECH STACK:
- React 18 (global `React`)
- Tailwind CSS CDN

BROWSER API SAFETY:
- CAMERA / MEDIA ACCESS: call `navigator.mediaDevices.getUserMedia(constraints)`
  directly — never chain `?.` on navigator, mediaDevices, or getUserMedia.
  Use `.then(fn).catch(fn)` chains or try/catch inside a regular helper function.
  Never put camera/media logic in a React component body — always in useEffect or
  an event handler. Count every {{ and }} after writing media code to ensure balance.

UNIQUENESS REQUIREMENT:
This site must look completely different from a generic SaaS template.
Specific requirements:
- Use the brand_color as a starting point but build a FULL palette around it
- The hero section layout must match hero_layout exactly — do not default to centered
- Section backgrounds must vary — not all white or all dark
- At least one section must use a gradient, pattern, or bold background color
- Typography sizes must be dramatic where appropriate — don't play it safe
- Interactive elements must have hover states that feel intentional
- The overall aesthetic must be immediately recognizable as {ctx.get('design_style', 'minimal')}

If someone looked at this site and could mistake it for any other site,
you have failed. Make it unmistakably this product.

Return ONE function named `App` that renders the full page body only.
The bootstrap hoists it with `if (typeof App === 'function') window.App = App;` after Babel.
Output ONLY raw JavaScript/JSX starting with `function App()`."""


def build_prompt(ctx: dict) -> str:
    """Return the full LLM prompt for landing-style builds (marketing_site or product_app)."""
    design_brief = str(ctx.get("_design_brief") or "")
    features_text = str(ctx.get("_features_text") or "")
    hero = str(ctx.get("_hero_image_instruction") or "")
    logo = str(ctx.get("_logo_image_instruction") or "")
    rag_injection = str(ctx.get("_rag_injection") or "")
    site_mode = resolve_site_mode(ctx)
    if site_mode == PRODUCT_APP:
        return _product(ctx, design_brief, features_text, hero, logo, rag_injection)
    return _marketing(ctx, design_brief, features_text, hero, logo, rag_injection)
