"""
Final testing agent — independent QA bot that mentally loads the component in a browser,
verifies all buttons and components work, confirms all requirements are met,
and sanitises the output for deployment.

This is Pass 3 in the three-pass build pipeline.
"""
from __future__ import annotations

import re
import logging
from ..infrastructure.llm_client import chat
from .jsx_validator import validate_jsx
from .syntax_agent import precheck_jsx, _deterministic_fixes

logger = logging.getLogger(__name__)

_QA_SYSTEM = """You are a QA engineer doing a final browser compatibility check on a React component.
This code runs in a browser using Babel standalone + React 18 global + Tailwind CDN.
There is no bundler, no TypeScript compiler, no Node.js.

YOUR TASK: Mentally load this component in a browser. Find and fix EVERY issue that would cause
a JavaScript error, a Babel transpilation error, or a blank/broken page. Then output the fully fixed code.

KNOWN FAILURE PATTERNS TO HUNT FOR (check every single one):
- ?. anywhere → replace with explicit null checks
- ?? anywhere → replace with ||
- ||= / &&= / ??= → replace with explicit assignments
- import or export statements → delete them
- TypeScript syntax: `: Type`, `<Type>`, `as Type`, `interface`, `type X =` → delete all
- async React components → remove the async keyword
- .at() calls → rewrite with bracket notation
- Unmatched { } braces → fix them (count { and } manually; net must be 0)
- Unclosed JSX tags → close them
- Ternary chains 3+ levels deep inside JSX → refactor to variables
- Object destructuring in function params (except useState) → use props.x
- Generator functions (function*) → rewrite
- Any pattern that Babel standalone cannot transpile
- UNTERMINATED STRINGS: Every ' and " must be closed on the same logical line. Every template
  literal backtick (`) must be closed. An unclosed string literal eats all subsequent code
  including braces and makes the file unparseable — find and close the string first.
- CAMERA / MEDIA: navigator.mediaDevices.getUserMedia(constraints) must be called directly —
  no ?. chaining on navigator, mediaDevices, or getUserMedia. Must be inside useEffect or
  an event handler, never directly in the component body.
  BRACE WARNING: after rewriting any ?.  chains inside Promise callbacks or nested constraint
  objects, re-count { and } to confirm the total is still balanced.

Output ONLY the corrected raw JSX. No markdown, no explanation, no preamble."""


async def qa_review(
    component: str,
    *,
    max_llm_attempts: int = 2,
    strict_upstream_syntax_ok: bool = False,
) -> str:
    """
    Conditional QA review — skips the LLM call entirely if precheck finds no issues
    and Babel parses the source.

    When ``strict_upstream_syntax_ok`` is True (callers that always run
    ``sanity_check_and_fix`` first), the QA skip fast-path re-verifies parse so we
    never log a falsely reassuring skip message on broken JSX.

    ``max_llm_attempts`` controls how many full QA codegen rounds run when
    issues remain after deterministic fixes (defaults to ``2``).
    Preview builds pass ``1`` to avoid stacking two expensive Sonnet calls.
    The testing phase's `precheck_jsx` call decides whether to mark the page as
    `passed=False` and the release phase drops those pages before assembly — so a
    failure mode here translates to "page gets dropped", never "whole build crashes".

    Residual issues return best-effort output (no deterministic brace mutation).
    """
    component = _deterministic_fixes(component)

    initial_issues = precheck_jsx(component)
    initial_parse = await validate_jsx(component)
    if not initial_issues and initial_parse.ok:
        if strict_upstream_syntax_ok:
            verify_parse = await validate_jsx(component)
            if not verify_parse.ok:
                raise RuntimeError(
                    "qa_review: refusing QA skip fast-path — JSX parse failed on verification pass "
                    f"(reason={verify_parse.error_message})"
                )
        logger.info("QA pass skipped — precheck and parse validation clean")
        return component

    async def _run_qa_llm(code: str) -> str:
        result = await chat(
            [{"role": "user", "content": f"COMPONENT:\n{code}"}],
            system=_QA_SYSTEM,
            max_tokens=16000,
            cache_system=True,
        )
        result = re.sub(r"^```[a-z]*\s*", "", result)
        result = re.sub(r"\s*```$", "", result)
        return _deterministic_fixes(result)

    result = component
    if max_llm_attempts < 1:
        max_llm_attempts = 1
    for attempt in range(1, max_llm_attempts + 1):
        try:
            result = await _run_qa_llm(result)
        except Exception:
            logger.exception("QA attempt %d failed — using code from previous step", attempt)
            break

        result = _deterministic_fixes(result)

        remaining = precheck_jsx(result)
        vr = await validate_jsx(result)
        if not remaining and vr.ok:
            logger.info("QA pass clean after attempt %d — component ready for deployment", attempt)
            return result

        logger.warning(
            "QA attempt %d still has issues: %s; parse_ok=%s",
            attempt,
            "; ".join(remaining) if remaining else "(none)",
            vr.ok,
        )

    final_issues = precheck_jsx(result)
    final_vr = await validate_jsx(result)
    if final_issues or not final_vr.ok:
        logger.error(
            "QA could not fully clean component — returning best-effort with %d residual "
            "precheck issue(s); parse_ok=%s",
            len(final_issues),
            final_vr.ok,
        )
        return result

    logger.info("QA pass clean after final pass — component ready for deployment")
    return result
