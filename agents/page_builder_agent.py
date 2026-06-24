"""
Page builder agent — generates individual page JSX from product context.
Owns the design system, brand colour logic, and the React shell wrapper.
One responsibility: turn a context dict into clean, deployable HTML for a single page.
"""
from __future__ import annotations

import os
import re
import json
import logging
from ..orchestration.build_modes import MARKETING_SITE, PRODUCT_APP, resolve_site_mode
from ..infrastructure.llm_client import chat, quality_model
from .syntax_agent import SyntaxAgentValidationError, sanity_check_and_fix, _deterministic_fixes
from .final_testing_agent import qa_review

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design system
# ---------------------------------------------------------------------------

_DESIGN_STYLE_RULES: dict[str, str] = {
    "editorial": (
        "Light background (bg-white or bg-stone-50), dark ink text (text-stone-900). "
        "Sections separated by thin dividers. Large, expressive headline font sizing (text-6xl+). "
        "Generous whitespace. Accent used sparingly — only on key CTAs and highlights. "
        "Cards: flat with subtle border-stone-200, no heavy shadows. "
        "Buttons: rounded-lg, not pill-shaped."
    ),
    "minimal": (
        "Near-white or off-white background (bg-zinc-50 or bg-white), monochromatic with single accent pop. "
        "Typography-led: let text hierarchy do the work, minimal decoration. "
        "Sections have maximum breathing room (py-32+). Icons replaced with clean SVG or nothing. "
        "Cards: very subtle bg-zinc-100 or bg-white with ring-1 ring-zinc-200. "
        "Buttons: rounded-md, restrained. No gradients except one subtle accent gradient on CTA."
    ),
    "bold": (
        "Dark background (bg-black or bg-zinc-950). Huge, high-contrast type — hero heading text-7xl or larger. "
        "Accent color used liberally: backgrounds, borders, text. Near-brutalist: think thick borders, "
        "offset shadows on cards (shadow-[4px_4px_0px] in accent color), tight spacing. "
        "Buttons: squared off (rounded-md or rounded-none), bold weight, uppercase text. "
        "Layout can be asymmetric — don't always center everything."
    ),
    "soft": (
        "Light pastel background (bg-[accent]-50 or bg-rose-50 etc.), warm and inviting. "
        "Rounded everything: rounded-3xl on cards, rounded-full on buttons and avatars. "
        "Soft drop shadows (shadow-lg in muted colors). Gradient backgrounds on hero (from-[accent]-100 to-white). "
        "Friendly typography sizes (not brutally large). Emoji or illustrated icons welcome. "
        "CTA buttons: filled with accent, no outline variants."
    ),
    "technical": (
        "Dark theme: bg-gray-950 or bg-[#0a0a0a]. Green/teal/violet accent on monospace elements. "
        "Code-block aesthetic: some text in font-mono. Grid lines as decoration (border-dashed border-white/5). "
        "Cards: dark bg-gray-900, ring-1 ring-white/10, small monospace labels. "
        "Sections can include terminal-style readouts or stat counters. "
        "Buttons: rounded-md, sometimes with a [>] or $ prefix in the label. Minimal animations."
    ),
    "luxury": (
        "Very dark background (bg-[#0c0c0c] or bg-stone-950). Accent in gold/amber/cream tones. "
        "Tight letter-spacing (tracking-widest) on headings and labels. All-caps section labels. "
        "Thin, elegant borders (border-amber-900/30). Cards: dark with subtle amber/gold ring. "
        "Generous negative space — never crowded. Typography: large but refined, not bombastic. "
        "Buttons: outlined or ghost style, never chunky filled shapes."
    ),
}

# Per-style body shell theming. Keys chosen to match _DESIGN_STYLE_RULES.
# body_class: applied to <body> so the page background + default text color
#             match the chosen design_style. Fixes the long-standing bug where
#             every site rendered on top of bg-black/text-white even when the
#             style called for a light background.
# font_stack_css: default family for body (Inter for most, serif/mono for the
#                 styles that need them). Scoped to `body` so Tailwind's
#                 font-mono / font-serif utilities continue to work on children.
# google_fonts: Google Fonts families to preload (comma-separated family specs).
# tailwind_font_families: JS object literal for tailwind.config.theme.extend.fontFamily
#                         so pages can use font-sans / font-display / font-mono / font-serif.
_STYLE_SHELL: dict[str, dict[str, str]] = {
    "editorial": {
        "body_class": "bg-stone-50 text-stone-900 antialiased",
        "font_stack_css": "'Fraunces', Georgia, serif",
        "google_fonts": "Fraunces:wght@400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['Fraunces', 'Georgia', 'serif'], "
            "serif: ['Fraunces', 'Georgia', 'serif'], "
            "mono: ['ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
    "minimal": {
        "body_class": "bg-zinc-50 text-zinc-900 antialiased",
        "font_stack_css": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@300;400;500;600;700;800;900",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['Inter', 'sans-serif'], "
            "serif: ['ui-serif', 'Georgia', 'serif'], "
            "mono: ['ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
    "bold": {
        "body_class": "bg-zinc-950 text-white antialiased",
        "font_stack_css": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['Space Grotesk', 'Inter', 'sans-serif'], "
            "serif: ['ui-serif', 'Georgia', 'serif'], "
            "mono: ['ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
    "soft": {
        "body_class": "bg-white text-stone-900 antialiased",
        "font_stack_css": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@300;400;500;600;700&family=DM+Serif+Display",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['DM Serif Display', 'Georgia', 'serif'], "
            "serif: ['DM Serif Display', 'Georgia', 'serif'], "
            "mono: ['ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
    "technical": {
        "body_class": "bg-[#0a0a0a] text-zinc-100 antialiased",
        "font_stack_css": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['Inter', 'sans-serif'], "
            "serif: ['ui-serif', 'Georgia', 'serif'], "
            "mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
    "luxury": {
        "body_class": "bg-stone-950 text-stone-100 antialiased",
        "font_stack_css": "'Inter', sans-serif",
        "google_fonts": "Inter:wght@300;400;500;600;700&family=Cormorant+Garamond:wght@400;500;600;700",
        "tailwind_font_families": (
            "sans: ['Inter', 'sans-serif'], "
            "display: ['Cormorant Garamond', 'Georgia', 'serif'], "
            "serif: ['Cormorant Garamond', 'Georgia', 'serif'], "
            "mono: ['ui-monospace', 'SFMono-Regular', 'monospace']"
        ),
    },
}


def _shell_theme(design_style: str) -> dict[str, str]:
    return _STYLE_SHELL.get(design_style, _STYLE_SHELL["minimal"])


def _preview_requirements(ctx: dict, site_mode: str, business_name: str) -> str:
    if site_mode == PRODUCT_APP:
        return (
            f"Complete multi-screen React SPA for {business_name} with working "
            "product experience as the default screen ('app'), working Login and Signup forms, "
            "Pricing page with 3 tiers and monthly/annual toggle, and a final Landing/conversion "
            "screen reached only via a CTA at the end of the product experience. "
            "React.useState-based routing with setCurrentPage. No waitlist captures anywhere "
            "except the final landing conversion screen."
        )
    return (
        f"Public-facing React website for {business_name}. Single-page marketing/site experience "
        "with a hero, proof/trust section, product-specific features, workflow/use-case content, "
        "final CTA, and at least one React.useState-driven interaction such as tabs, FAQ accordion, "
        "or pricing toggle. Must remain a website rather than a dashboard or auth app."
    )


_HERO_LAYOUT_INSTRUCTIONS: dict[str, str] = {
    "centered": (
        "Hero: full viewport height (min-h-screen), flex flex-col items-center justify-center text-center. "
        "Headline stacked above tagline, both centered. Two CTA buttons side-by-side below."
    ),
    "split-left": (
        "Hero: full viewport height, flex items-center. Left half: headline, tagline, CTAs (text-left). "
        "Right half: a styled mock UI block or abstract graphic built purely from Tailwind divs — "
        "e.g. a fake dashboard card, stat panel, or geometric shape. No <img> tags."
    ),
    "split-right": (
        "Hero: full viewport height, flex items-center. Right half: headline, tagline, CTAs (text-left on md+, centered on mobile). "
        "Left half: a styled mock UI or abstract graphic built from Tailwind divs. No <img> tags."
    ),
    "statement": (
        "Hero: full viewport height, flex flex-col justify-center. "
        "ONE enormous statement (text-8xl or larger on desktop, responsive down) that takes up most of the fold — "
        "could be the tagline or a bold claim. Product name smaller above it. CTAs below, left-aligned. "
        "Almost no other decoration."
    ),
    "cinematic": (
        "Hero: full viewport height, relative overflow-hidden. Dramatic radial or conic gradient background "
        "(e.g. from accent color fading to near-black). Content centered with text-center. "
        "Headline with bg-clip-text gradient. Subtle glowing orb divs (absolute, blur-3xl, opacity-20) "
        "as atmospheric background decoration."
    ),
}


def build_design_brief(ctx: dict) -> str:
    style = ctx.get("design_style", "minimal")
    brand_color = ctx.get("brand_color") or ctx.get("accent_color", "#6366F1")
    if not brand_color.startswith("#"):
        brand_color = f"#{brand_color}"
    hero = ctx.get("hero_layout", "centered")
    tone = ctx.get("tone", "professional")

    style_rules = _DESIGN_STYLE_RULES.get(style, _DESIGN_STYLE_RULES["minimal"])
    hero_instructions = _HERO_LAYOUT_INSTRUCTIONS.get(hero, _HERO_LAYOUT_INSTRUCTIONS["centered"])

    # Typography hints per style so the LLM reaches for the right utility class.
    # `font-display` is aliased in tailwind.config to the style's display face
    # (serif for editorial/soft/luxury, Space Grotesk for bold, Inter for the rest).
    _TYPE_HINTS = {
        "editorial": "Use font-display (serif) for all headings. Body stays font-sans (Inter).",
        "minimal":   "Use font-sans (Inter) throughout. Vary weight + size rather than family.",
        "bold":      "Use font-display (Space Grotesk) on hero/headlines, font-sans on body. Consider tracking-tight on large headings.",
        "soft":      "Use font-display (DM Serif Display) on hero headlines for warmth, font-sans on body copy.",
        "technical": "Use font-mono (JetBrains Mono) on labels, stat values, code snippets, badges. Headings remain font-sans.",
        "luxury":    "Use font-display (Cormorant Garamond) for headings with tracking-wide. Body font-sans but restrained.",
    }
    type_hint = _TYPE_HINTS.get(style, _TYPE_HINTS["minimal"])

    return f"""DESIGN SYSTEM:
Style: {style} — {style_rules}

Brand color: {brand_color}
The shell registers this hex as the Tailwind color `brand`. Prefer the named class — it is more
reliable than arbitrary values under the Tailwind CDN JIT:
  - Solid backgrounds:  bg-brand
  - Hover backgrounds:  hover:bg-brand/90
  - Text:               text-brand
  - Borders/rings:      border-brand  or  ring-1 ring-brand/40
  - Subtle tints:       bg-brand/10  bg-brand/5
  - Gradients:          from-brand to-brand/60
Arbitrary-value forms (bg-[{brand_color}] etc.) still work if you need the raw hex, but keep the
hex LITERAL — never build class names via template-literal interpolation, the CDN JIT cannot see them.
Do NOT use generic Tailwind color names (violet, indigo, etc.). Use ONLY the `brand` utility or the literal hex.

Typography:
- font-sans, font-display, font-mono, font-serif are all wired up in the shell for this style.
- {type_hint}

Tone: {tone} — let this inform copywriting energy and micro-interaction choices

Hero layout: {hero_instructions}

UNIVERSAL RULES:
- Tailwind utility classes exclusively — no inline styles
- Mobile first — stack to single column on small screens (sm: md: lg: breakpoints)
- Smooth hover transitions on all interactive elements (transition-all duration-200)
- NO placeholder images — build visual interest from Tailwind shapes, gradients, and text
- Generate real, specific content — no "Lorem ipsum" or generic filler text
- The page body background is already set by the shell for this style — do NOT wrap the
  whole page in bg-black or bg-white. Use transparent/section-level backgrounds instead."""


def _sanitize_component(code: str) -> str:
    """
    Strips things that break Babel standalone in a browser:
    import/export statements, 'use client'/'use strict' directives,
    and any prose preamble Claude adds before the first code definition.
    Does NOT trim to `function App` — multi-page builds define helper components before App.

    After line-level stripping, delegates to `_deterministic_fixes` from
    `syntax_agent` so all deterministic transforms (e.g. ``??`` → ``||``,
    ``||=`` expansion, simple ``?.`` rewriting, async component stripping) run
    in one consolidated pass instead of being duplicated here.
    """
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        # Pure directive / bare import lines — skip entirely.
        if stripped.startswith((
            "import ",
            "export {",
            "'use client'", '"use client"', "'use strict'", '"use strict"',
        )):
            continue
        # `export default function Foo` or `export default class Foo` —
        # strip only the `export default ` prefix so the function/class body
        # is preserved. Previously the whole line was skipped, which dropped
        # `function App()` when the LLM prefixed it with `export default`.
        if stripped.startswith("export default "):
            suffix = stripped[len("export default "):].lstrip()
            if suffix.startswith(("function ", "class ", "const ", "async function ")):
                # Re-indent: keep leading whitespace from original line.
                leading = line[: len(line) - len(line.lstrip())]
                line = leading + suffix
            else:
                # Bare `export default expr;` — nothing to salvage, skip.
                continue
        elif stripped.startswith("export function ") or stripped.startswith("export const "):
            line = line.replace("export function ", "function ", 1).replace("export const ", "const ", 1)
        lines.append(line)

    joined = "\n".join(lines)
    first_code = re.search(r"^(function |const |class |\/\/|<)", joined, re.MULTILINE)
    if first_code and first_code.start() > 0:
        joined = joined[first_code.start():]

    # Delegate all remaining deterministic transforms (including ?? → ||) to
    # syntax_agent._deterministic_fixes so the logic lives in one place.
    return _deterministic_fixes(joined)


def wrap_in_react_shell(
    component_code: str,
    business_name: str,
    design_style: str = "minimal",
    brand_color: str = "#6366F1",
    hero_image_url: str | None = None,
    logo_image_url: str | None = None,
    og_image_url: str = "",
    og_description: str = "",
    og_site_url: str = "",
) -> str:
    """
    Wraps Claude-generated React component JSX in a full HTML page with CDN imports.

    The shell is theme-aware:
      - body background + default text color come from the `design_style` (no more
        hardcoded dark theme that conflicts with light styles).
      - Google Fonts load a display/mono family appropriate to the style.
      - Tailwind gets a `brand` color + font-display/font-mono aliases so the LLM
        can reach for named utilities (`bg-brand`, `font-display`) instead of brittle
        interpolated class names.
      - The global font rule is scoped to `body` rather than `*`, so font-mono /
        font-serif Tailwind utilities actually apply to child elements.

    Nano Banana Pro assets
    ----------------------
    If `hero_image_url` / `logo_image_url` are provided (HTTPS URLs from
    Supabase Storage after :func:`design_agent.create_site_blueprint` uploads
    the Gemini PNGs), they're exposed to the runtime component code as the
    globals `HERO_IMAGE_URL` and `LOGO_IMAGE_URL`. Component code can check for
    them with `typeof HERO_IMAGE_URL !== 'undefined' && HERO_IMAGE_URL` and
    fall back to Tailwind-only compositions when they're empty. Keeping them as
    JS globals (rather than interpolating them into the JSX string) keeps the
    `<script id="app-source">` payload small and avoids quoting hazards.

    Open Graph
    ----------
    When `og_image_url` is provided, the <head> gets a full suite of Open
    Graph + Twitter Card meta tags so the page renders with a branded
    preview image when shared on iMessage / Slack / Twitter / LinkedIn /
    WhatsApp / Discord. `og_description` and `og_site_url` round out the
    card. Passing them in keeps this function pure — the caller decides
    what the image URL is (e.g. `site_url(slug)/og/<slug>.png`).
    """
    if not brand_color.startswith("#"):
        brand_color = f"#{brand_color}"
    theme = _shell_theme(design_style)
    clean_code = _sanitize_component(component_code)

    # json.dumps produces a safely quoted JS string literal. Empty strings for
    # missing assets so `if (HERO_IMAGE_URL) {…}` works uniformly.
    hero_js_literal = json.dumps(hero_image_url or "")
    logo_js_literal = json.dumps(logo_image_url or "")

    og_meta_block = ""
    if og_image_url:
        # Local import to avoid an import cycle if `og_image` ever needs to
        # pull anything from the agents package.
        from ..design.og_image import og_meta_tags

        og_meta_block = "  " + og_meta_tags(
            title=business_name,
            description=og_description or business_name,
            image_url=og_image_url,
            site_url=og_site_url or og_image_url,
        ) + "\n"
    # React dev builds (vs .production.min.js) are used intentionally here:
    #  * Error messages are readable. Prod is minified to cryptic "Minified
    #    React error #31" links that are useless to end-users and to us when
    #    diagnosing a bad LLM-generated page.
    #  * Size cost (~1.2 MB vs ~140 KB) is irrelevant — these are ~10 KB
    #    one-off marketing pages served through a CDN with long cache headers,
    #    and readability of the error is what actually matters when something
    #    goes wrong.
    #
    # CDN versions are pinned to the exact semver that was validated in CI so
    # a surprise upstream release cannot break existing deployed pages.  The
    # unpkg ?v=<hash> cache-busting suffix is intentionally omitted — semver
    # pins are stable enough and unpkg serves with long cache-control headers.
    #
    # Pinned versions:
    #   react / react-dom: 18.3.1  (latest stable 18.x as of 2025-Q1)
    #   @babel/standalone:  7.26.5 (react preset — env omitted; modern browsers)
    #   tailwindcss CDN:   3.4.x   (latest v3 — no semver pin in the CDN URL)
    #
    # When upgrading: bump all three in lockstep and re-run the test suite so
    # that precheck_jsx and Babel parse validation regressions surface before deploy.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{business_name}</title>
{og_meta_block}
  <script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone@7.26.5/babel.min.js" crossorigin></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family={theme['google_fonts']}&display=swap" rel="stylesheet" />
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            brand: '{brand_color}',
            'brand-light': '{brand_color}22',
            'brand-mid': '{brand_color}88',
          }},
          fontFamily: {{ {theme['tailwind_font_families']} }}
        }}
      }}
    }}
  </script>
  <style>
    body {{ font-family: {theme['font_stack_css']}; }}
    html {{ scroll-behavior: smooth; }}
    /* Inline error overlay — visibility controlled by JS (style.display). */
    #nw-error {{ display: none; }}
    /* Brand color exposed as a CSS custom property for use by the runtime
       hero-fallback injection below and by any component that needs it. */
    :root {{ --nw-brand: {brand_color}; }}
    /* Applied at runtime (see script below) when HERO_IMAGE_URL is empty and
       the LLM-generated hero section is near-black. Overrides bg-black /
       bg-gray-900 etc. with a branded gradient so the page isn't invisible. */
    .nw-hero-gradient-fallback {{
      background: linear-gradient(135deg, {brand_color} 0%, {brand_color}44 100%) !important;
    }}
  </style>
</head>
<body class="{theme['body_class']}">
  <div id="root"></div>
  <script>
    // Nano Banana Pro-generated imagery. Exposed as globals the React
    // component can read without us having to splice large base64 strings
    // into the JSX template below. Empty strings when unavailable; the
    // component code is expected to treat them as falsy.
    window.HERO_IMAGE_URL = {hero_js_literal};
    window.LOGO_IMAGE_URL = {logo_js_literal};
    var HERO_IMAGE_URL = window.HERO_IMAGE_URL;
    var LOGO_IMAGE_URL = window.LOGO_IMAGE_URL;

    // Runtime hero-fallback: when there is no hero image and the LLM chose a
    // dark Tailwind background (bg-black, bg-gray-900, etc.) the page renders
    // as a solid black rectangle.  After React mounts we scan the first
    // full-height section and, if its computed background is effectively black,
    // swap in a branded gradient so the page is always visible and on-brand.
    // This fires only when HERO_IMAGE_URL is empty so pages with a real image
    // are never affected.
    if (!window.HERO_IMAGE_URL) {{
      function __nwFixBlackHero() {{
        try {{
          // Target the first visually-full-height block (the hero section).
          var candidates = document.querySelectorAll(
            '#root section, #root [class*="h-screen"], #root [class*="min-h-screen"]'
          );
          if (!candidates.length) return;
          var hero = candidates[0];
          var bg = window.getComputedStyle(hero).backgroundColor;
          // rgb(0,0,0) = bg-black; very dark colours share the same channel range.
          var m = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
          if (m) {{
            var r = +m[1], g = +m[2], b = +m[3];
            if (r < 30 && g < 30 && b < 30) {{
              hero.classList.add('nw-hero-gradient-fallback');
            }}
          }}
        }} catch (_) {{}}
      }}
      // React mounts asynchronously — poll briefly until the DOM is populated.
      var __nwHeroFixAttempts = 0;
      var __nwHeroFixTimer = setInterval(function() {{
        if (++__nwHeroFixAttempts > 20) {{ clearInterval(__nwHeroFixTimer); return; }}
        var root = document.getElementById('root');
        if (root && root.children.length) {{
          clearInterval(__nwHeroFixTimer);
          __nwFixBlackHero();
        }}
      }}, 150);
    }}
  </script>
  <!-- Error overlay — shown only when the React app fails to mount.
       Styled to be readable on any background, with a reload shortcut and a
       clear action the user can take. Never shown during normal operation. -->
  <div id="nw-error" role="alert" aria-live="assertive"
       style="display:none;position:fixed;inset:0;z-index:9999;
              background:#0f0f0f;color:#f8fafc;
              font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
              padding:48px 40px;overflow:auto;box-sizing:border-box">
    <div style="max-width:680px;margin:0 auto">
      <p style="font-size:0.75rem;letter-spacing:0.08em;text-transform:uppercase;
                color:#94a3b8;margin-bottom:16px">Page load error</p>
      <h2 style="font-size:1.5rem;font-weight:700;margin:0 0 8px;color:#f1f5f9">
        Something went wrong loading this page.
      </h2>
      <p style="font-size:0.9rem;color:#94a3b8;margin:0 0 24px;line-height:1.6">
        This is likely a temporary issue. Try refreshing — if it keeps happening,
        the page is being updated and will be ready shortly.
      </p>
      <button onclick="location.reload()"
              style="display:inline-block;padding:10px 20px;background:#3b82f6;
                     color:#fff;border:none;border-radius:6px;font-size:0.875rem;
                     font-weight:600;cursor:pointer;margin-bottom:32px">
        Reload page
      </button>
      <details style="border-top:1px solid #1e293b;padding-top:20px">
        <summary style="font-size:0.75rem;color:#64748b;cursor:pointer;
                        margin-bottom:12px;list-style:none">
          Technical details
        </summary>
        <pre id="nw-error-body"
             style="white-space:pre-wrap;font-size:0.78rem;color:#f87171;
                    background:#1e293b;padding:16px;border-radius:6px;
                    overflow-x:auto;line-height:1.5;margin:0"></pre>
      </details>
    </div>
  </div>
  <script id="app-source" type="text/template">
{clean_code}
  </script>
  <script>
    (function () {{
      var rootEl = document.getElementById('root');
      var errEl = document.getElementById('nw-error');
      var errBody = document.getElementById('nw-error-body');
      var mounted = false;

      function showError(msg) {{
        if (errBody) errBody.textContent = String(msg || 'unknown error');
        if (errEl) errEl.style.display = 'block';
        if (rootEl) rootEl.style.display = 'none';
        // Surface in the console so headless visual QA / DevTools sees it.
        try {{ console.error('[nanowork render]', msg); }} catch (_) {{}}
      }}

      // Guard against CDN failure (React/Babel/Tailwind script didn't load).
      // When unpkg is unreachable the globals are undefined and we'd get a
      // cryptic ReferenceError instead of a helpful message.
      if (typeof React === 'undefined' || typeof ReactDOM === 'undefined') {{
        showError(
          'CDN scripts did not load (React or ReactDOM is undefined).\\n' +
          'This is usually a temporary network hiccup. Please refresh the page.\\n\\n' +
          'If you are in a restricted network environment, the page requires\\n' +
          'access to unpkg.com and cdn.tailwindcss.com.'
        );
        return;
      }}
      if (typeof Babel === 'undefined') {{
        showError(
          'CDN scripts did not load (Babel standalone is undefined).\\n' +
          'This is usually a temporary network hiccup. Please refresh the page.'
        );
        return;
      }}

      // Async / event-handler errors don't propagate through our try/catch
      // around eval() or past React's Error Boundary — they surface via
      // window.onerror. Catch them too so the user never stares at a blank page.
      window.addEventListener('error', function (ev) {{
        if (mounted) return;
        var m = (ev && ev.error && ev.error.stack) || (ev && ev.message) || 'unknown error';
        showError('Runtime error: ' + m);
      }});
      window.addEventListener('unhandledrejection', function (ev) {{
        if (mounted) return;
        var reason = ev && ev.reason;
        var m = (reason && reason.stack) || (reason && reason.message) || String(reason);
        showError('Unhandled promise rejection: ' + m);
      }});

      // Error Boundary — catches render errors thrown synchronously from any
      // descendant so the user gets our styled error page instead of a blank
      // screen + a cryptic react-dom stack in DevTools. Defined on window so
      // it's reachable from inside the eval'd, Babel-transpiled IIFE.
      window.__nw_showError = showError;
      window.__nw_ErrorBoundary = (function (R) {{
        function Boundary(props) {{
          R.Component.call(this, props);
          this.state = {{ error: null }};
        }}
        Boundary.prototype = Object.create(R.Component.prototype);
        Boundary.prototype.constructor = Boundary;
        Boundary.getDerivedStateFromError = function (error) {{
          return {{ error: error }};
        }};
        Boundary.prototype.componentDidCatch = function (error, info) {{
          try {{
            var msg = (error && error.stack) || (error && error.message) || String(error);
            window.__nw_showError && window.__nw_showError(msg);
          }} catch (_) {{}}
          try {{ console.error('[nanowork boundary]', error, info); }} catch (_) {{}}
        }};
        Boundary.prototype.render = function () {{
          if (this.state.error) return null;
          return this.props.children;
        }};
        return Boundary;
      }})(React);

      function runApp() {{
        var src = document.getElementById('app-source').textContent;
        var compiled;
        try {{
          compiled = Babel.transform(src, {{ presets: ['react'] }}).code;
        }} catch (e) {{
          showError('Compile error: ' + (e && e.message ? e.message : e));
          return;
        }}

        // Bridge the eval scope to the outer scope. Babel's env preset emits
        // "use strict" at the top of compiled output, and in strict mode
        // function declarations inside eval() do not leak to the surrounding
        // scope. We explicitly hoist the component declarations the agent is
        // expected to produce so the mount call can find them.
        var mountSrc = compiled + ";\\n" +
          "if (typeof App === 'function') window.App = App;\\n" +
          "if (typeof Nav === 'function') window.Nav = Nav;\\n" +
          "if (typeof Footer === 'function') window.Footer = Footer;\\n" +
          "if (typeof LandingPage === 'function') window.LandingPage = LandingPage;\\n" +
          "if (typeof window.App !== 'function') {{\\n" +
          "  window.__nw_showError('App component is missing or not a function. " +
          "Expected `function App() {{ ... }}` at the top level.');\\n" +
          "}} else {{\\n" +
          "  try {{\\n" +
          "    var __nwRoot = ReactDOM.createRoot(document.getElementById('root'));\\n" +
          "    __nwRoot.render(\\n" +
          "      React.createElement(window.__nw_ErrorBoundary, null, React.createElement(window.App))\\n" +
          "    );\\n" +
          "    window.__nw_mounted = true;\\n" +
          "  }} catch (__nwMountErr) {{\\n" +
          "    window.__nw_showError('Mount error: ' + ((__nwMountErr && __nwMountErr.stack) || (__nwMountErr && __nwMountErr.message) || __nwMountErr));\\n" +
          "  }}\\n" +
          "}}\\n";

        try {{
          // Single eval(compiled + mount glue): helpers hoisted onto window above.
          // eslint-disable-next-line no-eval
          eval(mountSrc);
        }} catch (e) {{
          showError('Runtime error: ' + ((e && e.stack) || (e && e.message) || e));
          return;
        }}

        if (window.__nw_mounted) mounted = true;
      }}

      if (document.readyState === 'loading') {{
        window.addEventListener('DOMContentLoaded', runApp);
      }} else {{
        runApp();
      }}
    }})();
  </script>
</body>
</html>"""


def _preview_speed_enabled() -> bool:
    """Pre-payment preview tweaks (skip syntax pass-three LLM, single QA LLM round)."""
    raw = os.getenv("PREVIEW_LEGACY_SYNTAX_PIPELINE", "").strip().lower()
    return raw not in ("1", "true", "yes")


async def _run_full_pipeline(
    component: str,
    requirements: str,
    business_name: str,
    design_style: str = "minimal",
    brand_color: str = "#6366F1",
    hero_image_url: str | None = None,
    logo_image_url: str | None = None,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    """Runs syntax_agent (passes 1–3) then final_testing QA, returns full HTML."""
    use_speed = preview_speed and _preview_speed_enabled()
    fixed = await sanity_check_and_fix(
        component,
        requirements,
        omit_pass_three_llm=use_speed,
        phone=log_phone,
        slug=log_slug,
    )
    reviewed = await qa_review(
        fixed,
        max_llm_attempts=1 if use_speed else 2,
        strict_upstream_syntax_ok=True,
    )
    return wrap_in_react_shell(
        reviewed,
        business_name,
        design_style,
        brand_color,
        hero_image_url=hero_image_url,
        logo_image_url=logo_image_url,
    )


async def generate_landing_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    """
    Produces the PRE-PAYMENT preview — not a marketing landing page, but a
    complete, working multi-screen React SPA that lets the founder (and their
    visitors) actually USE the product before hitting a conversion moment.

    The preview bundles everything into ONE HTML file so we don't need the
    full SDLC pipeline just to show an experience. Structure:

      - Default screen ("app"): a real, interactive product experience built
        specifically for this business — dashboards, tools, browse flows,
        whatever matches the product shape. NO marketing, NO waitlist.
      - Auth screens: working Login + Signup forms with React.useState
        submission states.
      - Pricing screen: 3 tiers tailored to the pricing model we know about.
      - Landing/conversion screen: the marketing-style "here's the pitch"
        view that was previously the ONLY preview. It's reached via a
        "Get Started" / "Ready to launch?" CTA at the end of the app
        experience — conversion happens AFTER the user has experienced the
        product, not before.
    Generates a preview landing page:
      1. Asks Claude for the MAIN CONTENT only — hero, problem, features,
         waitlist. No in-page nav, no in-page footer.
      2. Wraps that content with the shared Nav + Footer from `ui_components`
         so every preview (and every post-payment build) has the SAME
         persistent navbar + footer shape. That fixes the long-standing
         complaint that preview pages had ad-hoc navs and sometimes no footer
         at all.
      3. Injects the Nano Banana Pro hero image into the shell as a JS global
         (`HERO_IMAGE_URL`), and asks the LLM to render it as a backdrop in
         the hero section when it is available. When the image isn't available
         (no API key, Gemini down, etc.), the component falls back to a
         Tailwind gradient exactly like before.

    Returns a complete HTML string ready to serve.
    """
    from .prompts.landing_prompt import SYSTEM_PROMPT

    # Keyword-based design template lookup
    import json as _json

    DESIGN_TEMPLATES = {
        "tech": {"colors":{"primary":"#7C3AED","secondary":"#3B82F6","background":"#0F0F0F","surface":"#1A1A1A","text":"#F9FAFB"},"fonts":{"heading":"Inter","body":"Inter"},"tone":"professional"},
        "consumer": {"colors":{"primary":"#F97316","secondary":"#FCD34D","background":"#FFFBF0","surface":"#FFF7ED","text":"#1C1917"},"fonts":{"heading":"Poppins","body":"Inter"},"tone":"friendly"},
        "finance": {"colors":{"primary":"#1E3A5F","secondary":"#10B981","background":"#F8FAFC","surface":"#FFFFFF","text":"#0F172A"},"fonts":{"heading":"Merriweather","body":"Inter"},"tone":"authoritative"},
        "health": {"colors":{"primary":"#16a34a","secondary":"#15803d","background":"#0a0a0a","surface":"#111111","text":"#f0fdf4"},"fonts":{"heading":"Space Grotesk","body":"Inter"},"tone":"athletic"},
        "marketplace": {"colors":{"primary":"#111827","secondary":"#EAB308","background":"#FFFFFF","surface":"#F9FAFB","text":"#111827"},"fonts":{"heading":"Space Grotesk","body":"Inter"},"tone":"direct"},
        "creator": {"colors":{"primary":"#EC4899","secondary":"#8B5CF6","background":"#09090B","surface":"#18181B","text":"#FAFAFA"},"fonts":{"heading":"Space Grotesk","body":"Inter"},"tone":"expressive"},
        "food": {"colors":{"primary":"#991B1B","secondary":"#D97706","background":"#FFFBF0","surface":"#FEF3C7","text":"#1C1917"},"fonts":{"heading":"Playfair Display","body":"Lato"},"tone":"inviting"},
        "gaming": {"colors":{"primary":"#00FF88","secondary":"#0EA5E9","background":"#050505","surface":"#0A0A0A","text":"#F0FFF4"},"fonts":{"heading":"Orbitron","body":"Rajdhani"},"tone":"intense"},
    }

    INDUSTRY_KEYWORDS = {
        "tech": ["software","app","platform","saas","tool","ai","api","developer","code","tech","data","cloud"],
        "consumer": ["social","community","network","connect","share","mobile","consumer","lifestyle","dating","friend"],
        "finance": ["finance","bank","invest","money","pay","crypto","tax","budget","loan","credit","wealth"],
        "health": ["health","wellness","fitness","medical","mental","therapy","workout","diet","calorie","nutrition","weight","exercise","gym","yoga","meditation","sleep","steps","macro"],
        "marketplace": ["marketplace","buy","sell","shop","store","ecommerce","retail","product","vendor","listing"],
        "creator": ["creator","artist","design","portfolio","gallery","music","video","stream","content","media"],
        "food": ["food","restaurant","recipe","cooking","meal","delivery","kitchen","chef","dining","cuisine"],
        "gaming": ["game","gaming","esports","play","quest","battle","arena","tournament","player","stream"],
    }

    # Match build context to template
    build_text = (
        str(ctx.get("description", "")) + " " +
        str(ctx.get("solution", "")) + " " +
        str(ctx.get("problem", "")) + " " +
        str(ctx.get("business_name", "")) + " " +
        str(ctx.get("audience", ""))
    ).lower()

    matched_template = None
    max_matches = 0
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in build_text)
        if matches > max_matches:
            max_matches = matches
            matched_template = industry

    template = DESIGN_TEMPLATES.get(matched_template or "tech", DESIGN_TEMPLATES["tech"])

    design_brief = build_design_brief(ctx)
    business_name = ctx["business_name"]
    site_mode = resolve_site_mode(ctx, default=MARKETING_SITE)
    design_style = ctx.get("design_style", "minimal")
    brand_color = ctx.get("brand_color") or ctx.get("accent_color", "#6366F1")
    hero_image_url = ctx.get("hero_image_url")
    logo_image_url = ctx.get("logo_image_url")

    has_product_nav = site_mode == PRODUCT_APP

    # Two separate, composable instructions — one for the hero photograph and
    # one for the logomark. Historically only the hero instruction existed, so
    # Claude never actually rendered the Nano Banana Pro logo even when one
    # was available: Nano Banana would run, the logo URL would sit in
    # `window.LOGO_IMAGE_URL`, and the LLM would still draw a Tailwind dot in
    # its in-screen header because nothing in the prompt told it otherwise.
    # Splitting the instructions and *always* mentioning both globals in the
    # prompt fixes that — when the global is empty the component falls back
    # to Tailwind shapes, when it is populated the Nano Banana asset renders.
    # These instructions are always unconditional — the image URLs are injected
    # as JS globals at serve time (potentially AFTER this JSX is generated when
    # imagery runs in parallel with page generation). The LLM must always emit
    # the runtime guard so the images render when the globals are populated later.
    hero_image_instruction = (
        "A Nano Banana Pro hero photograph may be available in the JS global "
        "`HERO_IMAGE_URL` by the time this page is served. "
        "ALWAYS write the hero section to handle both cases at runtime: "
        "render `{HERO_IMAGE_URL && <img src={HERO_IMAGE_URL} alt='' "
        "className='absolute inset-0 w-full h-full object-cover' />}` "
        "plus a dark gradient overlay inside a `relative overflow-hidden` container, "
        "AND provide a vivid Tailwind gradient fallback "
        "(`bg-gradient-to-br from-brand via-violet-600 to-indigo-800` or similar) "
        "that shows when `HERO_IMAGE_URL` is empty. "
        "CRITICAL: NEVER use `bg-black`, `bg-gray-900`, `bg-slate-900`, "
        "`bg-neutral-900`, or `bg-zinc-900` as the hero's primary background — "
        "without a photograph it renders as a solid black rectangle. "
        "The gradient fallback must be colorful and readable on its own."
    )

    logo_image_instruction = (
        "A Nano Banana Pro logomark may be available in the JS global `LOGO_IMAGE_URL` "
        "by serve time. WHEREVER the product name appears with a decorative mark "
        "(in-app header, signup card, pricing tier icons, CTAs), ALWAYS write: "
        "`{LOGO_IMAGE_URL ? <img src={LOGO_IMAGE_URL} alt='' className='w-8 h-8 rounded-lg object-cover' /> "
        ": <div className='w-8 h-8 rounded-lg bg-brand' />}` "
        "next to the name. This ensures the branded asset renders when available "
        "without requiring a page rebuild."
    )

    features = ctx.get("features")
    if isinstance(features, list):
        features_text = ", ".join(str(f) for f in features)
    else:
        features_text = str(features or "")

    from .prompts import landing_prompt

    # Build design template injection
    rag_injection = f"""
DESIGN TEMPLATE GUIDANCE (industry: {matched_template or 'tech'}):
Use these as creative direction — adapt them to match the actual design_style chosen:
• Color palette: primary {template['colors']['primary']}, secondary {template['colors']['secondary']}
• Typography: {template['fonts']['heading']} for headings, {template['fonts']['body']} for body
• Tone: {template['tone']}
• Background strategy: {template['colors']['background']} base, {template['colors']['surface']} for cards/sections
• Text color: {template['colors']['text']}

IMPORTANT: These are SUGGESTIONS based on the industry. The actual brand_color from the context
takes precedence. Use this template to inform secondary colors, typography choices, and tone."""

    prompt = landing_prompt.build_prompt({
        **ctx,
        "_design_brief": design_brief,
        "_features_text": features_text,
        "_hero_image_instruction": hero_image_instruction,
        "_logo_image_instruction": logo_image_instruction,
        "_rag_injection": rag_injection,
    })

    # Single LLM call generates the full multi-screen SPA (App + its screens).
    # Historically there used to be a second chat() call with a marketing-landing
    # prompt whose `App` function overwrote the multi-screen SPA produced by the
    # first — the net effect was a waitlist-style landing page sneaking into the
    # preview and wiping out the interactive product experience. That also
    # showed up in the deployed renders: the second prompt generated a page
    # assuming an outer wrapper that doesn't exist in this flow, which is why
    # positioning under the shared Nav looked off. Removed the duplicate call;
    # the multi-screen SPA from the first prompt is what we use directly.
    #
    # If this call fails AFTER the llm_client retries are exhausted (e.g. a
    # sustained Anthropic 529 storm, an auth error, or a runtime hiccup), we
    # fall back to a static, ctx-driven preview rather than letting the
    # exception cascade up to the user as "hit a snag building your page".
    # The user still gets a working multi-screen SPA preview — just with more
    # templated copy instead of the bespoke LLM output. That's strictly better
    # than a 30-60s wait that ends in a generic error message.
    print(f"[DEBUG] design_style={ctx.get('design_style')} brand_color={ctx.get('brand_color')} hero_layout={ctx.get('hero_layout')}", flush=True)
    try:
        component = await chat(
            [{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
            max_tokens=16000,
            model=quality_model(),
        )
    except Exception as e:
        logger.exception(
            "generate_landing_page: primary LLM call failed — serving static fallback preview (%s)", e
        )
        from .static_fallbacks import build_static_landing_html
        return build_static_landing_html(ctx)
    # Apply early deterministic sanitization before the assembly step so that
    # import/export lines, markdown fences, 'use client' directives, and other
    # known bad patterns don't make it into the assembled JSX string that's fed
    # to sanity_check_and_fix.  Previously these were only stripped inside
    # wrap_in_react_shell (which runs AFTER the syntax/QA pipeline) meaning the
    # precheck could report false positives for patterns already removed, and
    # the LLM fix passes would waste tokens on prose preamble or ES-module syntax.
    component = _sanitize_component(component)

    # No nav/footer assembly — Claude generates the complete page including
    # its own custom navbar and footer matched to the product's visual identity.
    assembled = component

    requirements = _preview_requirements(ctx, site_mode, business_name)
    # The syntax/QA sub-pipeline can itself issue LLM calls (if the precheck
    # finds an issue in the LLM's JSX). If all of those calls also fail, fall
    # back to the static preview so the user still gets a working page.
    try:
        return await _run_full_pipeline(
            assembled,
            requirements,
            business_name,
            design_style=design_style,
            brand_color=brand_color,
            hero_image_url=hero_image_url,
            logo_image_url=logo_image_url,
            preview_speed=preview_speed,
            log_phone=log_phone,
            log_slug=log_slug,
        )
    except SyntaxAgentValidationError:
        raise
    except Exception as e:
        logger.exception(
            "generate_landing_page: syntax/QA pipeline failed — serving static fallback preview (%s)", e
        )
        from .static_fallbacks import build_static_landing_html
        return build_static_landing_html(ctx)


def _page_display_name(ctx: dict) -> str:
    return str(ctx.get("business_name") or ctx.get("tool_name") or "Nanowork")


def _brand_and_style(ctx: dict) -> tuple[str, str]:
    brand_color = ctx.get("brand_color") or ctx.get("accent_color", "#6366F1")
    if not str(brand_color).startswith("#"):
        brand_color = f"#{brand_color}"
    design_style = ctx.get("design_style", "minimal")
    return str(brand_color), str(design_style)


async def _generate_from_type_prompt(
    ctx: dict,
    *,
    prompt_builder,
    requirements: str,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
    max_tokens: int = 16000,
) -> str:
    """Single-screen generators: type-specific prompt → syntax/QA → shell."""
    brand_color, design_style = _brand_and_style(ctx)
    prompt = prompt_builder(ctx)
    try:
        component = await chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            model=quality_model(),
        )
    except Exception as e:
        logger.exception(
            "generate_%s_page: primary LLM call failed — static landing fallback (%s)",
            ctx.get("build_type", "page"),
            e,
        )
        from .static_fallbacks import build_static_landing_html

        return build_static_landing_html(ctx)
    component = _sanitize_component(component)
    try:
        return await _run_full_pipeline(
            component,
            requirements,
            _page_display_name(ctx),
            design_style=design_style,
            brand_color=brand_color,
            hero_image_url=ctx.get("hero_image_url"),
            logo_image_url=ctx.get("logo_image_url"),
            preview_speed=preview_speed,
            log_phone=log_phone,
            log_slug=log_slug,
        )
    except SyntaxAgentValidationError:
        raise
    except Exception as e:
        logger.exception(
            "generate_%s_page: syntax/QA failed — static landing fallback (%s)",
            ctx.get("build_type", "page"),
            e,
        )
        from .static_fallbacks import build_static_landing_html

        return build_static_landing_html(ctx)


async def generate_tool_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    """Single-page calculator / converter / widget (tool taxonomy)."""
    from .prompts import tool_prompt

    brand_color, design_style = _brand_and_style(ctx)
    prompt = tool_prompt.build_prompt(ctx)
    print(f"[DEBUG-TOOL] design_style={ctx.get('design_style')} brand_color={ctx.get('brand_color')} flow_kind={ctx.get('flow_kind')}", flush=True)
    try:
        component = await chat(
            [{"role": "user", "content": prompt}],
            max_tokens=16000,
            model=quality_model(),
        )
    except Exception as e:
        logger.exception("generate_tool_page: primary LLM call failed — static tool fallback (%s)", e)
        from .static_fallbacks import build_static_tool_html

        return build_static_tool_html(ctx)
    component = _sanitize_component(component)
    outputs_summary = ", ".join(str(o) for o in (ctx.get("outputs") or [])) or "calculated results"
    requirements = (
        "Three screens: tool (default), pricing, about. "
        "Tool screen: live calculation + earnings estimator with interactive inputs. "
        "Pricing screen: 3 tiers + revenue callout. "
        "About screen: 3-step explainer. "
        "React.useState routing. All JSX balanced. No broken tags."
    )
    try:
        return await _run_full_pipeline(
            component,
            requirements,
            ctx.get("tool_name", "Tool"),
            design_style=design_style,
            brand_color=brand_color,
            hero_image_url=ctx.get("hero_image_url"),
            logo_image_url=ctx.get("logo_image_url"),
            preview_speed=preview_speed,
            log_phone=log_phone,
            log_slug=log_slug,
        )
    except SyntaxAgentValidationError:
        raise
    except Exception as e:
        logger.exception("generate_tool_page: syntax/QA failed — static tool fallback (%s)", e)
        from .static_fallbacks import build_static_tool_html

        return build_static_tool_html(ctx)


async def generate_form_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import form_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=form_prompt.build_prompt,
        requirements="Lead form with validation, submit success state, preview disclaimer sentence.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


async def generate_directory_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import directory_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=directory_prompt.build_prompt,
        requirements="Directory/list page with sample cards and optional text filter.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


async def generate_portfolio_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import portfolio_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=portfolio_prompt.build_prompt,
        requirements="Portfolio: hero, work grid, about, contact.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


async def generate_booking_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import booking_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=booking_prompt.build_prompt,
        requirements="Booking form with date, time slots, confirmation state.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


async def generate_app_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import app_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=app_prompt.build_prompt,
        requirements="Multi-screen demo via useState only; dashboard + detail screens; sample data.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
        max_tokens=16000,
    )


async def generate_info_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import info_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=info_prompt.build_prompt,
        requirements="Informational sections with h2; optional TOC for 4+ sections.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


async def generate_other_page(
    ctx: dict,
    *,
    preview_speed: bool = False,
    log_phone: str | None = None,
    log_slug: str | None = None,
) -> str:
    from .prompts import other_prompt

    return await _generate_from_type_prompt(
        ctx,
        prompt_builder=other_prompt.build_prompt,
        requirements="Direct best-effort implementation of the user's ask; single file App.",
        preview_speed=preview_speed,
        log_phone=log_phone,
        log_slug=log_slug,
    )


# Back-compat alias — orchestrator waitlist tool path used this name.
generate_tool_app = generate_tool_page
