"""
Static, LLM-free preview builders.

Purpose
-------
`generate_landing_page` and `generate_tool_app` both make a large `chat()` call
(max_tokens=16000 / 8000) to synthesise a multi-screen SPA. `llm_client.chat`
retries transient Anthropic errors (529 overload, 429 rate limit, connection
blips) — but once retries are exhausted, the exception cascades up through
`build_and_store_page` → `_finish`, surfacing to the user as the dreaded
"hit a snag building your page 😓 our team's been notified" message.

At that point the user has sat through 30-60s of "researching the market and
designing your site now ✨" only to be told the build failed. Retrying later
means re-entering the whole flow. That's the exact symptom operators keep
reporting: the build completes right up to the preview page, then snags.

The fix in this module is graceful degradation: when the LLM is unavailable,
render a polished, static preview directly from the ctx dict. It's not as
rich as the LLM output, but it is:
  - A real, interactive multi-screen SPA (Home / Login / Signup / Pricing /
    Landing) wired with React.useState routing, matching the LLM path's shape.
  - Styled from ctx ``design_style`` + ``brand_color``, with the same shared
    Nav + Footer the LLM path uses.
  - Guaranteed to ship — no LLM calls, no chance of another "hit a snag".

The caller (`generate_landing_page` / `generate_tool_app`) tries the LLM path
first and only falls back to these if the LLM path raises.
"""
from __future__ import annotations

import json
import logging
from typing import Sequence

from ..orchestration.build_modes import MARKETING_SITE, PRODUCT_APP, resolve_site_mode
from .page_builder_agent import wrap_in_react_shell
from .ui_components import render_nav_and_footer, nav_content_offset_for

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _js_str(value: object) -> str:
    """
    Safely serialise a Python string/other into a JS string literal that can
    be inlined into JSX without quoting hazards.

    `json.dumps` handles the quoting/escaping (quotes, backslashes, newlines,
    control chars, unicode). On top of that we neutralise sequences that
    HTML parsers look for regardless of JS string context:

      * `</script>` / `</SCRIPT>` — terminates the outer <script> block the
        HTML shell wraps us in (Chrome terminates *any* script block on
        `</script>`, even `<script type="text/template">`).
      * `<!--` — starts an HTML comment which can swallow the rest of the
        script body in some browsers.

    The ``<\\/`` trick: JS strings parse ``\\/`` as a literal ``/``, so the
    value at runtime is byte-identical, but the shipped bytes no longer
    contain the dangerous ``</`` sequence verbatim. Same technique JSON
    encoders use for script-safe output.
    """
    escaped = json.dumps("" if value is None else str(value))
    escaped = escaped.replace("</", "<\\/")
    escaped = escaped.replace("<!--", "<\\!--")
    return escaped


def _jsx_text(value: object) -> str:
    """
    Escape a value so it's safe to place as literal text inside JSX (e.g.
    between tags). JSX treats `{` and `}` as expression delimiters, and `<`
    starts a tag — escape those plus HTML-specials so broken copy can't
    unbalance the page.
    """
    s = "" if value is None else str(value)
    return (
        s.replace("\\", "\\\\")
        .replace("{", "{'{'}")
        .replace("}", "{'}'}")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# The repo's `precheck_jsx` tag opener/regex heuristic and older brace-count logic
# produced false positives on JSX with apostrophes in text. Static fallback JSX
# is hand-authored to precheck-clean. We don't run the full pipeline on this path
# (it bypasses `_run_full_pipeline`), but the tests call precheck directly against the generated JSX to lock in a
# "Babel-clean static preview" contract — which is well worth the one-character
# swap. Using the typographic right-single-quote (U+2019) also reads better on
# screen. Wrap all hand-written JSX text through this helper.
_APOSTROPHE = "\u2019"


def _smartquote(s: str) -> str:
    """Replaces ASCII apostrophes with U+2019 so they don't look like JS strings."""
    return s.replace("'", _APOSTROPHE)


def _features_list(ctx: dict) -> list[str]:
    feats = ctx.get("features")
    if isinstance(feats, list) and feats:
        return [str(f) for f in feats[:6]]
    if isinstance(feats, str) and feats.strip():
        return [p.strip() for p in feats.split(",") if p.strip()][:6]
    return ["Fast setup", "Built for your audience", "Crafted with care"]


# ---------------------------------------------------------------------------
# Static landing SPA
# ---------------------------------------------------------------------------

def _build_static_landing_jsx(ctx: dict) -> str:
    """
    Produces a self-contained multi-screen SPA JSX using only ctx data.
    Mirrors the screen set from `generate_landing_page` (app/login/signup/
    pricing/landing) but with fixed copy drawn from ctx rather than the LLM.

    The returned JSX is plain JS — no TypeScript, no optional chaining, no
    nullish coalescing, no imports — so Babel standalone transpiles it
    without issue. We deliberately bypass `sanity_check_and_fix` / `qa_review`
    on this path (see `build_static_landing_html`) because:

      1. The template is author-controlled and known-good.
      2. The primary LLM call has just failed; calling Claude *again* to
         sanity-check code we know is fine would risk re-entering the same
         failure mode and surfacing "hit a snag" to the user after all.

    Note: the repo's `precheck_jsx` heuristic has known false positives on
    JSX closing tags (`</Tag>`) because its regex-vs-division scanner treats
    `<` as a regex-prefix character, making `</` look like the start of a
    regex literal. That's fine — Babel itself is the real compiler and this
    JSX compiles cleanly. The tests pin down the actual runtime contract:
    that the generated JSX produces a mounted SPA with the expected screens.
    """
    # All ctx-derived strings go through `_js_str` so they're placed inside
    # JSX via React's `{expression}` slot — they can therefore contain any
    # characters (including apostrophes) without tripping brittle text heuristics.
    business_name = _js_str(ctx.get("business_name", "Your Product"))
    tagline = _js_str(ctx.get("tagline") or _smartquote("Built for what's next."))
    problem = _js_str(ctx.get("problem") or _smartquote("Getting this done is harder than it should be."))
    solution = _js_str(ctx.get("solution") or _smartquote("We're making it simple."))
    audience = _js_str(ctx.get("audience") or "Builders like you")
    differentiator = _js_str(
        ctx.get("differentiator") or "Opinionated defaults, zero setup, designed for momentum."
    )

    features = _features_list(ctx)
    features_literal = "[" + ", ".join(_js_str(f) for f in features) + "]"

    return f"""
function AppScreen(props) {{
  const businessName = {business_name};
  const tagline = {tagline};
  const solution = {solution};
  const audience = {audience};
  const features = {features_literal};

  const [filter, setFilter] = React.useState('');
  const items = [
    {{ name: 'Overview', detail: tagline }},
    {{ name: 'For ' + audience, detail: solution }},
    {{ name: 'What you get', detail: features.join(' · ') }},
    {{ name: 'Ready to ship', detail: 'No bloat. No ceremony. Start today.' }},
    {{ name: 'Built to scale', detail: 'Grow without re-platforming.' }},
    {{ name: 'Trusted by', detail: 'Early teams getting real traction.' }}
  ];
  const filtered = items.filter(function (it) {{
    return filter === '' || (it.name + ' ' + it.detail).toLowerCase().indexOf(filter.toLowerCase()) !== -1;
  }});

  return (
    <div className="min-h-screen">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-2 text-xl font-semibold">
            {{LOGO_IMAGE_URL ? (
              <img src={{LOGO_IMAGE_URL}} alt="" className="w-8 h-8 rounded-lg object-cover" />
            ) : (
              <span className="inline-block w-2 h-2 rounded-full bg-brand"></span>
            )}}
            <span>{{businessName}}</span>
          </div>
          <div className="flex gap-3">
            <button onClick={{function () {{ props.setCurrentPage('pricing'); }}}}
                    className="px-3 py-1.5 rounded-md border border-current/20 text-sm hover:bg-current/5 transition-all">Pricing</button>
            <button onClick={{function () {{ props.setCurrentPage('login'); }}}}
                    className="px-3 py-1.5 rounded-md border border-current/20 text-sm hover:bg-current/5 transition-all">Log in</button>
            <button onClick={{function () {{ props.setCurrentPage('signup'); }}}}
                    className="px-3 py-1.5 rounded-md bg-brand text-white text-sm hover:bg-brand/90 transition-all">Sign up</button>
          </div>
        </div>

        {{HERO_IMAGE_URL ? (
          <div className="relative overflow-hidden rounded-3xl mb-10 aspect-[16/9] max-h-[420px] ring-1 ring-current/10">
            <img src={{HERO_IMAGE_URL}} alt="" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/20 to-black/60"></div>
            <div className="relative p-8 md:p-12 h-full flex flex-col justify-end text-white">
              <h1 className="text-4xl md:text-6xl font-display font-bold tracking-tight max-w-3xl drop-shadow">{{tagline}}</h1>
              <p className="mt-3 text-base md:text-lg opacity-90 max-w-2xl">{{solution}}</p>
            </div>
          </div>
        ) : (
          <div className="mb-10">
            <h1 className="text-5xl md:text-6xl font-display font-bold tracking-tight mb-4">{{tagline}}</h1>
            <p className="text-lg opacity-70 max-w-2xl">{{solution}}</p>
          </div>
        )}}

        <input
          type="text"
          value={{filter}}
          onChange={{function (e) {{ setFilter(e.target.value); }}}}
          placeholder="Search what you will get"
          className="w-full md:w-96 px-4 py-3 rounded-lg border border-current/20 bg-transparent mb-8 focus:outline-none focus:ring-2 focus:ring-brand/40"
        />

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mb-16">
          {{filtered.map(function (it, idx) {{
            return (
              <div key={{idx}} className="p-6 rounded-xl border border-current/10 hover:border-brand/40 transition-all">
                <div className="text-sm font-mono opacity-50 mb-2">0{{idx + 1}}</div>
                <div className="text-lg font-semibold mb-1">{{it.name}}</div>
                <div className="opacity-70 text-sm">{{it.detail}}</div>
              </div>
            );
          }})}}
        </div>

        <div className="p-10 rounded-2xl bg-brand/10 border border-brand/20 text-center">
          <h2 className="text-3xl font-display font-bold mb-2">Make {{businessName}} yours.</h2>
          <p className="opacity-70 mb-6">Spin up your account and get the full experience.</p>
          <button onClick={{function () {{ props.setCurrentPage('landing'); }}}}
                  className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">
            Get started →
          </button>
        </div>
      </div>
    </div>
  );
}}

function LoginScreen(props) {{
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [submitted, setSubmitted] = React.useState(false);

  if (submitted) {{
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md w-full text-center">
          <h2 className="text-2xl font-semibold mb-2">You\u2019re in.</h2>
          <p className="opacity-70 mb-6">Welcome back to {business_name}.</p>
          <button onClick={{function () {{ props.setCurrentPage('app'); }}}}
                  className="px-5 py-2 rounded-lg bg-brand text-white">Continue</button>
        </div>
      </div>
    );
  }}

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="max-w-md w-full">
        <button onClick={{function () {{ props.setCurrentPage('app'); }}}} className="text-sm opacity-60 mb-6 hover:opacity-100">← Back to app</button>
        <h2 className="text-3xl font-display font-bold mb-6">Log in</h2>
        <div className="space-y-4">
          <input type="email" value={{email}} onChange={{function (e) {{ setEmail(e.target.value); }}}}
                 placeholder="Email" className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent"></input>
          <input type="password" value={{password}} onChange={{function (e) {{ setPassword(e.target.value); }}}}
                 placeholder="Password" className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent"></input>
          <button onClick={{function () {{ setSubmitted(true); }}}}
                  className="w-full px-4 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">Log in</button>
          <div className="text-sm opacity-60 text-center">
            <span>Forgot password?</span>
            <span className="mx-2">·</span>
            <button onClick={{function () {{ props.setCurrentPage('signup'); }}}} className="underline">Need an account? Sign up</button>
          </div>
        </div>
      </div>
    </div>
  );
}}

function SignupScreen(props) {{
  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [agreed, setAgreed] = React.useState(false);
  const [submitted, setSubmitted] = React.useState(false);

  if (submitted) {{
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md w-full text-center">
          <h2 className="text-2xl font-semibold mb-2">Welcome aboard.</h2>
          <p className="opacity-70 mb-6">Your account is ready. Let\u2019s go.</p>
          <button onClick={{function () {{ props.setCurrentPage('app'); }}}}
                  className="px-5 py-2 rounded-lg bg-brand text-white">Open the app</button>
        </div>
      </div>
    );
  }}

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="max-w-md w-full">
        <button onClick={{function () {{ props.setCurrentPage('app'); }}}} className="text-sm opacity-60 mb-6 hover:opacity-100">← Back to app</button>
        <h2 className="text-3xl font-display font-bold mb-6">Create your account</h2>
        <div className="space-y-4">
          <input value={{name}} onChange={{function (e) {{ setName(e.target.value); }}}}
                 placeholder="Full name" className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent"></input>
          <input type="email" value={{email}} onChange={{function (e) {{ setEmail(e.target.value); }}}}
                 placeholder="Email" className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent"></input>
          <input type="password" value={{password}} onChange={{function (e) {{ setPassword(e.target.value); }}}}
                 placeholder="Create password" className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent"></input>
          <label className="flex items-center gap-2 text-sm opacity-80">
            <input type="checkbox" checked={{agreed}} onChange={{function (e) {{ setAgreed(e.target.checked); }}}}></input>
            <span>I agree to the terms and privacy policy.</span>
          </label>
          <button onClick={{function () {{ if (agreed) {{ setSubmitted(true); }} }}}}
                  className="w-full px-4 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all disabled:opacity-50">Create account</button>
          <div className="text-sm opacity-60 text-center">
            <button onClick={{function () {{ props.setCurrentPage('login'); }}}} className="underline">Have an account? Log in</button>
          </div>
        </div>
      </div>
    </div>
  );
}}

function PricingScreen(props) {{
  const [annual, setAnnual] = React.useState(false);
  const tiers = [
    {{ name: 'Starter', monthly: 0, note: 'To explore the product' }},
    {{ name: 'Growth', monthly: 29, note: 'For small teams shipping weekly', popular: true }},
    {{ name: 'Scale', monthly: 99, note: 'For serious workloads' }}
  ];
  return (
    <div className="min-h-screen px-6 py-12">
      <div className="max-w-5xl mx-auto">
        <button onClick={{function () {{ props.setCurrentPage('app'); }}}} className="text-sm opacity-60 mb-6 hover:opacity-100">← Back to app</button>
        <h2 className="text-4xl font-display font-bold mb-2 text-center">Simple pricing.</h2>
        <p className="opacity-70 text-center mb-8">Choose the plan that matches where you are today.</p>

        <div className="flex items-center justify-center gap-3 mb-10">
          <span className={{'text-sm ' + (annual ? 'opacity-50' : 'font-semibold')}}>Monthly</span>
          <button onClick={{function () {{ setAnnual(!annual); }}}}
                  className={{'w-12 h-6 rounded-full relative transition-all ' + (annual ? 'bg-brand' : 'bg-current/20')}}>
            <span className={{'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-all ' + (annual ? 'translate-x-6' : '')}}></span>
          </button>
          <span className={{'text-sm ' + (annual ? 'font-semibold' : 'opacity-50')}}>Annual <span className="opacity-60">(20% off)</span></span>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {{tiers.map(function (tier, idx) {{
            const price = annual ? Math.round(tier.monthly * 12 * 0.8) : tier.monthly;
            const unit = annual ? '/yr' : '/mo';
            return (
              <div key={{idx}} className={{'p-8 rounded-2xl border transition-all ' + (tier.popular ? 'border-brand ring-2 ring-brand/30' : 'border-current/15')}}>
                {{tier.popular ? <div className="text-xs font-semibold text-brand uppercase tracking-widest mb-2">Most popular</div> : null}}
                <div className="text-xl font-semibold mb-1">{{tier.name}}</div>
                <div className="opacity-60 text-sm mb-4">{{tier.note}}</div>
                <div className="text-4xl font-display font-bold mb-1">${{price}}<span className="text-base opacity-60 font-normal">{{unit}}</span></div>
                <button onClick={{function () {{ props.setCurrentPage('signup'); }}}}
                        className="mt-6 w-full px-4 py-2.5 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">Get {{tier.name}}</button>
              </div>
            );
          }})}}
        </div>
      </div>
    </div>
  );
}}

function LandingScreen(props) {{
  const businessName = {business_name};
  const tagline = {tagline};
  const problem = {problem};
  const solution = {solution};
  const differentiator = {differentiator};
  const features = {features_literal};

  return (
    <div className="min-h-screen">
      <div className="max-w-5xl mx-auto px-6 py-20">
        <button onClick={{function () {{ props.setCurrentPage('app'); }}}} className="text-sm opacity-60 mb-10 hover:opacity-100">← Back to the app</button>

        {{HERO_IMAGE_URL ? (
          <div className="relative overflow-hidden rounded-3xl mb-10 aspect-[16/9] max-h-[480px] ring-1 ring-current/10">
            <img src={{HERO_IMAGE_URL}} alt="" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/30 to-black/70"></div>
            <div className="relative p-8 md:p-12 h-full flex flex-col justify-end text-white">
              <h1 className="text-4xl md:text-6xl font-display font-bold tracking-tight max-w-3xl drop-shadow">{{tagline}}</h1>
              <p className="mt-3 text-base md:text-lg opacity-90 max-w-2xl">{{solution}}</p>
              <div className="mt-6">
                <button onClick={{function () {{ props.setCurrentPage('signup'); }}}}
                        className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">Create your account</button>
              </div>
            </div>
          </div>
        ) : (
          <React.Fragment>
            <h1 className="text-5xl md:text-7xl font-display font-bold tracking-tight mb-4">{{tagline}}</h1>
            <p className="text-lg md:text-xl opacity-80 max-w-2xl mb-8">{{solution}}</p>
            <button onClick={{function () {{ props.setCurrentPage('signup'); }}}}
                    className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">Create your account</button>
          </React.Fragment>
        )}}

        <div className="mt-20 grid md:grid-cols-3 gap-6">
          {{features.slice(0, 3).map(function (f, idx) {{
            return (
              <div key={{idx}} className="p-6 rounded-xl border border-current/10">
                <div className="text-sm font-mono opacity-50 mb-3">0{{idx + 1}}</div>
                <div className="text-lg font-semibold mb-1">{{f}}</div>
                <div className="opacity-70 text-sm">{{differentiator}}</div>
              </div>
            );
          }})}}
        </div>

        <div className="mt-20 p-10 rounded-2xl bg-brand/10 border border-brand/20 text-center">
          <h3 className="text-2xl font-display font-semibold mb-2">Ready when you are.</h3>
          <p className="opacity-70 mb-6">Join {{businessName}} and get moving today.</p>
          <button onClick={{function () {{ props.setCurrentPage('signup'); }}}}
                  className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">Sign up</button>
        </div>

        <div className="mt-16 text-sm opacity-60">
          <div className="mb-1"><span className="font-semibold">The problem:</span> {{problem}}</div>
          <div><span className="font-semibold">Who it is for:</span> {audience}</div>
        </div>
      </div>
    </div>
  );
}}

function LandingPage(props) {{
  const [currentPage, setCurrentPage] = React.useState('app');
  const setPage = props && props.setCurrentPage ? props.setCurrentPage : setCurrentPage;
  const page = currentPage;

  if (page === 'login')   return <LoginScreen setCurrentPage={{setCurrentPage}} />;
  if (page === 'signup')  return <SignupScreen setCurrentPage={{setCurrentPage}} />;
  if (page === 'pricing') return <PricingScreen setCurrentPage={{setCurrentPage}} />;
  if (page === 'landing') return <LandingScreen setCurrentPage={{setCurrentPage}} />;
  return <AppScreen setCurrentPage={{setCurrentPage}} />;
}}
"""


def _build_static_marketing_jsx(ctx: dict) -> str:
    business_name = _js_str(ctx.get("business_name", "Your Product"))
    tagline = _js_str(ctx.get("tagline") or _smartquote("A polished website, ready to launch."))
    problem = _js_str(ctx.get("problem") or _smartquote("Your audience needs a clearer reason to choose you."))
    solution = _js_str(ctx.get("solution") or _smartquote("We turn your offer into a sharp, conversion-ready website."))
    audience = _js_str(ctx.get("audience") or "Your ideal customers")
    differentiator = _js_str(
        ctx.get("differentiator") or "Clear positioning, credible proof, and strong calls to action."
    )
    features = _features_list(ctx)
    features_literal = "[" + ", ".join(_js_str(f) for f in features) + "]"

    return f"""
function LandingPage() {{
  const businessName = {business_name};
  const tagline = {tagline};
  const problem = {problem};
  const solution = {solution};
  const audience = {audience};
  const differentiator = {differentiator};
  const features = {features_literal};

  return (
    <div className="min-h-screen">
      <section className="max-w-6xl mx-auto px-6 pt-12 pb-20">
        <div className="grid lg:grid-cols-[1.2fr,0.8fr] gap-12 items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-brand/20 bg-brand/5 px-4 py-2 text-sm font-medium text-brand">
              <span className="inline-block w-2 h-2 rounded-full bg-brand"></span>
              Website first impression
            </div>
            <h1 className="mt-6 text-5xl md:text-7xl font-display font-bold tracking-tight">
              {{tagline}}
            </h1>
            <p className="mt-6 text-lg md:text-xl opacity-80 max-w-2xl">
              {{solution}}
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <button className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">
                Book intro call
              </button>
              <button className="px-6 py-3 rounded-lg border border-current/15 hover:bg-current/5 transition-all">
                See the work
              </button>
            </div>
            <div className="mt-8 text-sm opacity-65">
              Built for {{audience}}
            </div>
          </div>

          <div className="relative overflow-hidden rounded-3xl border border-current/10 bg-gradient-to-br from-brand/10 via-white/0 to-brand/5 p-8">
            {{HERO_IMAGE_URL ? (
              <div className="relative overflow-hidden rounded-2xl aspect-[4/5]">
                <img src={{HERO_IMAGE_URL}} alt="" className="absolute inset-0 w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-b from-black/5 via-black/15 to-black/50"></div>
              </div>
            ) : (
              <div className="grid gap-4">
                <div className="rounded-2xl border border-current/10 bg-white/70 p-5">
                  <div className="text-sm font-mono opacity-50 mb-2">Positioning</div>
                  <div className="text-xl font-semibold">{{businessName}}</div>
                  <div className="mt-2 opacity-70 text-sm">{{differentiator}}</div>
                </div>
                <div className="rounded-2xl border border-current/10 bg-white/70 p-5">
                  <div className="text-sm font-mono opacity-50 mb-2">Audience</div>
                  <div className="text-lg font-semibold">{{audience}}</div>
                  <div className="mt-2 opacity-70 text-sm">{{problem}}</div>
                </div>
              </div>
            )}}
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid md:grid-cols-3 gap-6">
          {{features.map(function (feature, idx) {{
            return (
              <div key={{idx}} className="rounded-2xl border border-current/10 p-6 bg-white/40">
                <div className="text-sm font-mono opacity-50 mb-4">0{{idx + 1}}</div>
                <div className="text-xl font-semibold mb-2">{{feature}}</div>
                <div className="opacity-70 text-sm">{{differentiator}}</div>
              </div>
            );
          }})}}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="rounded-3xl border border-current/10 p-8 bg-white/40">
            <div className="text-sm font-mono opacity-50 mb-3">The challenge</div>
            <h2 className="text-3xl font-display font-bold mb-4">Why this needs a better website</h2>
            <p className="opacity-80 text-base leading-7">{{problem}}</p>
          </div>
          <div className="rounded-3xl border border-brand/20 p-8 bg-brand/10">
            <div className="text-sm font-mono text-brand mb-3">The solution</div>
            <h2 className="text-3xl font-display font-bold mb-4">What visitors should understand instantly</h2>
            <p className="opacity-80 text-base leading-7">{{solution}}</p>
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-24">
        <div className="rounded-[2rem] border border-current/10 px-8 py-12 text-center bg-white/50">
          <div className="inline-flex items-center gap-2 justify-center mb-4 text-brand font-medium">
            {{LOGO_IMAGE_URL ? (
              <img src={{LOGO_IMAGE_URL}} alt="" className="w-8 h-8 rounded-lg object-cover" />
            ) : (
              <span className="inline-block w-2 h-2 rounded-full bg-brand"></span>
            )}}
            <span>{{businessName}}</span>
          </div>
          <h3 className="text-3xl md:text-4xl font-display font-bold">Ready to turn attention into action?</h3>
          <p className="mt-4 opacity-75 max-w-2xl mx-auto">
            Lead with a story, build trust fast, and guide the right people toward the next step.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-4">
            <button className="px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:bg-brand/90 transition-all">
              Book intro call
            </button>
            <button className="px-6 py-3 rounded-lg border border-current/15 hover:bg-current/5 transition-all">
              See the work
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}}
"""


def build_static_landing_html(ctx: dict) -> str:
    """
    Returns a complete, deployable HTML string for a preview landing when the
    LLM path fails. Wraps the static SPA JSX in the same shared Nav + Footer
    and React shell the LLM path uses, so the user-facing chrome looks
    identical — just with more generic copy.
    """
    business_name = ctx.get("business_name", "Your Product")
    # Preserve the historical fallback shape (multi-screen app preview) unless
    # the caller explicitly inferred or requested a marketing website. This
    # keeps outage-path tests and paid-user preview promotion stable while still
    # honouring the new explicit website mode.
    site_mode = (
        resolve_site_mode(ctx, default=PRODUCT_APP)
        if "site_mode" in ctx or "project_type" in ctx or "build_idea" in ctx or "description" in ctx
        else PRODUCT_APP
    )
    design_style = ctx.get("design_style", "minimal")
    brand_color = ctx.get("brand_color") or ctx.get("accent_color", "#6366F1")
    has_product_nav = site_mode == PRODUCT_APP

    nav_jsx, footer_jsx, nav_variant, _footer_variant = render_nav_and_footer(
        business_name=business_name,
        design_style=design_style,
        first_page="LandingPage",
        nav_items=[("LandingPage", "Home")],
        has_login=has_product_nav,
        has_signup=has_product_nav,
        has_pricing=has_product_nav,
        nav_variant=ctx.get("nav_variant"),
        footer_variant=ctx.get("footer_variant"),
    )
    content_offset = nav_content_offset_for(nav_variant)

    landing_jsx = (
        _build_static_landing_jsx(ctx)
        if site_mode == PRODUCT_APP
        else _build_static_marketing_jsx(ctx)
    )

    app_shell = f"""function App() {{
  const [currentPage, setCurrentPage] = React.useState('LandingPage');
  return (
    <div className="min-h-screen">
      <Nav currentPage={{currentPage}} setCurrentPage={{setCurrentPage}} />
      <div className="{content_offset}">
        <LandingPage setCurrentPage={{setCurrentPage}} />
      </div>
      <Footer setCurrentPage={{setCurrentPage}} />
    </div>
  );
}}"""

    assembled = "\n\n".join([
        "// ── Static fallback preview (LLM unavailable) ──",
        nav_jsx,
        footer_jsx,
        landing_jsx,
        app_shell,
    ])

    # Skip the syntax/QA pipeline entirely — the JSX is author-controlled,
    # already plain-JS-compatible, and we don't want a secondary LLM call
    # right after the primary one has been failing.
    return wrap_in_react_shell(
        assembled,
        business_name,
        design_style=design_style,
        brand_color=brand_color,
        hero_image_url=ctx.get("hero_image_url"),
        logo_image_url=ctx.get("logo_image_url"),
    )


# ---------------------------------------------------------------------------
# Static tool-app fallback
# ---------------------------------------------------------------------------

def _build_static_tool_jsx(ctx: dict) -> str:
    """
    Produces a self-contained single-screen tool app JSX built purely from
    ctx["inputs"] + ctx["outputs"]. The fallback tool is deliberately simple:
    each numeric input gets a <input type=number>, each text input a text
    field, each output shows the sum of all numeric inputs. That's crude but
    it's a working interactive tool instead of an error message.
    """
    tool_name = _js_str(ctx.get("tool_name", "Tool"))
    description = _js_str(ctx.get("description", ""))

    inputs = ctx.get("inputs") or [{"label": "Input", "type": "number"}]
    if not isinstance(inputs, list):
        inputs = [{"label": "Input", "type": "number"}]
    outputs = ctx.get("outputs") or ["Result"]
    if not isinstance(outputs, list):
        outputs = [str(outputs)]

    inputs_literal = (
        "["
        + ", ".join(
            "{{ label: {label}, type: {typ} }}".format(
                label=_js_str(inp.get("label", f"Input {i + 1}") if isinstance(inp, dict) else str(inp)),
                typ=_js_str((inp.get("type") if isinstance(inp, dict) else "number") or "number"),
            )
            for i, inp in enumerate(inputs)
        )
        + "]"
    )
    outputs_literal = "[" + ", ".join(_js_str(str(o)) for o in outputs) + "]"

    return f"""
function App() {{
  const toolName = {tool_name};
  const description = {description};
  const inputs = {inputs_literal};
  const outputs = {outputs_literal};

  const [values, setValues] = React.useState(inputs.map(function () {{ return ''; }}));

  function setAt(i, v) {{
    const next = values.slice();
    next[i] = v;
    setValues(next);
  }}
  function reset() {{
    setValues(inputs.map(function () {{ return ''; }}));
  }}

  const numericSum = values.reduce(function (acc, v) {{
    const n = parseFloat(v);
    return isNaN(n) ? acc : acc + n;
  }}, 0);

  return (
    <div className="min-h-screen">
      <div className="sticky top-0 z-10 border-b border-current/10 backdrop-blur bg-white/60">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="text-lg font-semibold">{{toolName}}</div>
          <button onClick={{reset}} className="px-3 py-1.5 rounded-md border border-current/20 text-sm hover:bg-current/5">Reset</button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-display font-bold mb-2">{{toolName}}</h1>
        <p className="opacity-70 mb-8">{{description}}</p>

        <div className="grid gap-4 mb-10">
          {{inputs.map(function (inp, i) {{
            return (
              <label key={{i}} className="block">
                <div className="text-sm font-medium mb-1">{{inp.label}}</div>
                <input
                  type={{inp.type === 'text' ? 'text' : 'number'}}
                  value={{values[i]}}
                  onChange={{function (e) {{ setAt(i, e.target.value); }}}}
                  placeholder={{'Enter ' + inp.label.toLowerCase()}}
                  className="w-full px-4 py-3 rounded-lg border border-current/20 bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/40"
                ></input>
              </label>
            );
          }})}}
        </div>

        <div className="p-6 rounded-xl border border-brand/30 bg-brand/5">
          <div className="text-sm font-semibold uppercase tracking-widest text-brand mb-3">Result</div>
          <div className="space-y-1">
            {{outputs.map(function (label, i) {{
              return (
                <div key={{i}} className="flex items-center justify-between">
                  <div className="opacity-70">{{label}}</div>
                  <div className="text-xl font-semibold">{{numericSum.toLocaleString(undefined, {{ maximumFractionDigits: 2 }})}}</div>
                </div>
              );
            }})}}
          </div>
        </div>

        <div className="mt-10 text-xs opacity-50 text-center">Built with Nanowork AI</div>
      </div>
    </div>
  );
}}
"""


def build_static_tool_html(ctx: dict) -> str:
    """
    Returns a complete, deployable HTML string for a preview tool when the
    LLM path fails. Uses the same React shell + brand color theming as the
    LLM path — the only visible difference is less-bespoke copy + math logic.
    """
    tool_name = ctx.get("tool_name", "Tool")
    design_style = ctx.get("design_style", "minimal")
    brand_color = ctx.get("brand_color") or ctx.get("accent_color", "#4f46e5")

    return wrap_in_react_shell(
        _build_static_tool_jsx(ctx),
        tool_name,
        design_style=design_style,
        brand_color=brand_color,
        hero_image_url=ctx.get("hero_image_url"),
        logo_image_url=ctx.get("logo_image_url"),
    )


__all__: Sequence[str] = (
    "build_static_landing_html",
    "build_static_tool_html",
)
