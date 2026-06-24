"""
Build Orchestrator — Integrates multi-agent orchestration into the build pipeline.

Wraps existing orchestrator_agent.py functions with the new AgentOrchestrator
for usage tracking, delegation, and approval flows.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..core.agents.orchestration import (
    AgentOrchestrator,
    AgentMode,
    AgentArtifact,
    AgentCall,
    register_agent,
)

logger = logging.getLogger(__name__)


async def build_with_orchestration(
    phone_number: str,
    ctx: dict,
    mode: AgentMode = AgentMode.SEMI_AUTONOMOUS,
    credits: int = 100,
    approval_callback: Optional[callable] = None,
) -> tuple[str, dict]:
    """
    Build an app using the multi-agent orchestration framework.

    Args:
        phone_number: User's phone number
        ctx: Build context
        mode: Agent autonomy mode (semi_autonomous or fully_autonomous)
        credits: Available agent credits
        approval_callback: Function to call when approval needed

    Returns:
        (url, usage_summary)
    """
    orchestrator = AgentOrchestrator(
        phone_number=phone_number,
        mode=mode,
        credits=credits,
        approval_callback=approval_callback,
    )

    # Delegate to build agent (which may in turn delegate to design, SEO, etc.)
    build_artifact = await orchestrator.delegate(
        "build_agent",
        ctx,
        requesting_agent=None,  # Root call
    )

    # Save usage to DB for billing
    await orchestrator.save_usage_to_db()

    usage_summary = orchestrator.get_usage_summary()

    if build_artifact.status == "success":
        url = build_artifact.data.get("url", "")
        return url, usage_summary
    else:
        error = build_artifact.metadata.get("error", "Build failed")
        raise RuntimeError(f"Build failed: {error}")


@register_agent("build_agent", credits_cost=50)
async def build_agent(
    ctx: dict,
    orchestrator: Optional[AgentOrchestrator] = None,
) -> AgentArtifact:
    """
    Main build agent — coordinates app generation with sub-agent delegation.

    Can delegate to:
      - design_agent (brand imagery, design tokens)
      - seo_agent (meta tags, structured data, content optimization)
      - scraper_agent (competitor analysis if URL provided)
    """
    from .orchestrator_agent import build_full_functional_app

    build_type = ctx.get("build_type", "app")

    try:
        # Run the existing build pipeline
        if build_type == "app":
            url, spec = await build_full_functional_app(
                ctx.get("phone_number", ""),
                ctx,
            )

            # After build completes, delegate to SEO agent for optimization
            # This only happens if we have an orchestrator (meaning agent mode is enabled)
            if orchestrator:
                logger.info("Build agent delegating to SEO agent for post-build optimization")

                seo_artifact = await orchestrator.delegate(
                    "seo_agent",
                    {
                        "html": spec.get("_generated_html", ""),  # if we stored it
                        "business_name": ctx.get("business_name", ""),
                        "description": ctx.get("description", ""),
                        "url": url,
                        "pages": [{"path": p, "priority": 0.8} for p in spec.get("pages", {}).keys()],
                    },
                    requesting_agent="build_agent",
                )

                return AgentArtifact(
                    agent_name="build_agent",
                    status="success",
                    data={
                        "url": url,
                        "spec": spec,
                        "seo_optimization": seo_artifact.data,
                    },
                    metadata={
                        "build_type": build_type,
                        "delegated_to": ["seo_agent"],
                    },
                    sub_artifacts=[seo_artifact],
                )

            return AgentArtifact(
                agent_name="build_agent",
                status="success",
                data={"url": url, "spec": spec},
                metadata={"build_type": build_type},
            )

        else:
            # Non-app builds (landing pages, etc.)
            from .orchestrator_agent import build_and_store_page

            url, discount_code = await build_and_store_page(
                ctx.get("phone_number", ""),
                ctx,
            )

            return AgentArtifact(
                agent_name="build_agent",
                status="success",
                data={"url": url, "discount_code": discount_code},
                metadata={"build_type": build_type},
            )

    except Exception as exc:
        logger.exception("Build agent failed")
        return AgentArtifact(
            agent_name="build_agent",
            status="failed",
            data={},
            metadata={"error": str(exc), "build_type": build_type},
        )


@register_agent("design_agent", credits_cost=15)
async def design_agent(
    ctx: dict,
    orchestrator: Optional[AgentOrchestrator] = None,
) -> AgentArtifact:
    """
    Design agent — generates brand imagery and design tokens.

    Can be invoked standalone or delegated to by build_agent.
    """
    from .design_agent import create_site_blueprint

    try:
        blueprint = await create_site_blueprint(ctx, preview_build=False)

        return AgentArtifact(
            agent_name="design_agent",
            status="success",
            data=blueprint,
        )

    except Exception as exc:
        logger.exception("Design agent failed")
        return AgentArtifact(
            agent_name="design_agent",
            status="failed",
            data={},
            metadata={"error": str(exc)},
        )
