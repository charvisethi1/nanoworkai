"""
Example usage of the multi-agent orchestration system.

Demonstrates:
1. Semi-autonomous mode with approval callbacks
2. Fully autonomous mode
3. Agent-to-agent delegation
4. Usage tracking and billing
"""
import asyncio
from nanowork_mobile.core.agents.orchestration import (
    AgentOrchestrator,
    AgentMode,
    AgentCall,
)


# ============================================================================
# Example 1: Semi-Autonomous Build with Approval Callback
# ============================================================================

async def ask_user_approval(call: AgentCall) -> bool:
    """
    Approval callback for semi-autonomous mode.

    In a real app, this would:
    - Send SMS to user: "Agent 'seo_agent' wants to optimize your site (20 credits). Approve? Y/N"
    - Wait for user response
    - Return True/False based on user's answer

    For this example, we auto-approve SEO and design agents, reject others.
    """
    print(f"\n[APPROVAL REQUEST]")
    print(f"  Agent: {call.agent_name}")
    print(f"  Requested by: {call.requesting_agent or 'root'}")
    print(f"  Cost: {call.credits_cost} credits")
    print(f"  Context keys: {list(call.context.keys())}")

    # Auto-approve SEO and design agents for demo
    if call.agent_name in ["seo_agent", "design_agent"]:
        print(f"  Decision: ✅ APPROVED")
        return True
    else:
        print(f"  Decision: ❌ REJECTED")
        return False


async def example_semi_autonomous_build():
    """Example: Build with semi-autonomous mode."""
    print("=" * 80)
    print("Example 1: Semi-Autonomous Build")
    print("=" * 80)

    # Create orchestrator
    orchestrator = AgentOrchestrator(
        phone_number="+15551234567",
        mode=AgentMode.SEMI_AUTONOMOUS,
        credits=100,
        approval_callback=ask_user_approval,
    )

    # Build context
    ctx = {
        "phone_number": "+15551234567",
        "business_name": "Joe's Coffee Shop",
        "description": "Local Portland coffee shop with ethically sourced beans",
        "build_type": "app",
    }

    # Delegate to build agent
    # Build agent will internally delegate to SEO agent (requires approval)
    print("\n[DELEGATING] to build_agent...")
    build_artifact = await orchestrator.delegate(
        "build_agent",
        ctx,
    )

    print(f"\n[BUILD RESULT]")
    print(f"  Status: {build_artifact.status}")
    print(f"  URL: {build_artifact.data.get('url', 'N/A')}")

    # Show usage summary
    summary = orchestrator.get_usage_summary()
    print(f"\n[USAGE SUMMARY]")
    print(f"  Credits used: {summary['credits_used']}/{summary['initial_credits']}")
    print(f"  Credits remaining: {summary['credits_remaining']}")
    print(f"  Total calls: {summary['total_calls']}")
    print(f"  Completed: {summary['completed_calls']}")
    print(f"  Failed: {summary['failed_calls']}")
    print(f"  Rejected: {summary['rejected_calls']}")

    print(f"\n[CALL HISTORY]")
    for call in summary['call_history']:
        print(f"  - {call['agent']} (requested by {call['requested_by'] or 'root'})")
        print(f"    Status: {call['status']}, Cost: {call['cost']} credits")

    # Save usage to DB for billing
    await orchestrator.save_usage_to_db()
    print("\n✅ Usage saved to database")


# ============================================================================
# Example 2: Fully Autonomous Build
# ============================================================================

async def example_fully_autonomous_build():
    """Example: Build with fully autonomous mode (no approvals needed)."""
    print("\n" + "=" * 80)
    print("Example 2: Fully Autonomous Build")
    print("=" * 80)

    # Create orchestrator with fully autonomous mode
    orchestrator = AgentOrchestrator(
        phone_number="+15559876543",
        mode=AgentMode.FULLY_AUTONOMOUS,
        credits=1000,  # Higher credit limit for premium users
    )

    ctx = {
        "phone_number": "+15559876543",
        "business_name": "TechFlow SaaS",
        "description": "Project management tool for remote teams",
        "build_type": "app",
    }

    print("\n[DELEGATING] to build_agent (no approvals needed)...")
    build_artifact = await orchestrator.delegate(
        "build_agent",
        ctx,
    )

    print(f"\n[BUILD RESULT]")
    print(f"  Status: {build_artifact.status}")
    print(f"  Sub-agents called: {len(build_artifact.sub_artifacts)}")
    for sub in build_artifact.sub_artifacts:
        print(f"    - {sub.agent_name}: {sub.status}")

    summary = orchestrator.get_usage_summary()
    print(f"\n[USAGE SUMMARY]")
    print(f"  Credits used: {summary['credits_used']}")
    print(f"  Credits remaining: {summary['credits_remaining']}")


# ============================================================================
# Example 3: Direct Agent Delegation (No Build)
# ============================================================================

async def example_seo_only():
    """Example: Run SEO agent standalone without building."""
    print("\n" + "=" * 80)
    print("Example 3: SEO Agent Standalone")
    print("=" * 80)

    orchestrator = AgentOrchestrator(
        phone_number="+15551112222",
        mode=AgentMode.FULLY_AUTONOMOUS,
        credits=50,
    )

    # Existing HTML to optimize
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>My Site</title>
    </head>
    <body>
        <h1>Welcome to My Coffee Shop</h1>
        <p>We serve the best coffee in Portland.</p>
    </body>
    </html>
    """

    ctx = {
        "html": html,
        "business_name": "Portland Coffee Co",
        "description": "Artisan coffee roaster in Portland",
        "url": "https://portlandcoffee.nanowork.app",
        "pages": [
            {"path": "/", "priority": 1.0},
            {"path": "/menu", "priority": 0.8},
            {"path": "/about", "priority": 0.6},
        ],
    }

    print("\n[DELEGATING] to seo_agent...")
    seo_artifact = await orchestrator.delegate(
        "seo_agent",
        ctx,
    )

    print(f"\n[SEO RESULT]")
    print(f"  Status: {seo_artifact.status}")
    print(f"  Optimizations applied: {seo_artifact.data.get('optimizations_applied', [])}")

    if meta := seo_artifact.data.get("meta_tags"):
        print(f"\n  Meta Tags:")
        print(f"    Title: {meta.get('title')}")
        print(f"    Description: {meta.get('description')[:80]}...")
        print(f"    Keywords: {', '.join(meta.get('keywords', []))}")

    if sitemap := seo_artifact.data.get("sitemap_xml"):
        print(f"\n  Sitemap generated: {len(sitemap)} chars")

    summary = orchestrator.get_usage_summary()
    print(f"\n[USAGE] Credits used: {summary['credits_used']}/{summary['initial_credits']}")


# ============================================================================
# Example 4: Competitor Analysis with Agent Chaining
# ============================================================================

async def example_competitor_analysis():
    """Example: Scrape competitor site, analyze SEO, generate insights."""
    print("\n" + "=" * 80)
    print("Example 4: Competitor Analysis (Agent Chaining)")
    print("=" * 80)

    orchestrator = AgentOrchestrator(
        phone_number="+15553334444",
        mode=AgentMode.FULLY_AUTONOMOUS,
        credits=200,
    )

    ctx = {
        "url": "https://example-competitor.com",
        "analyze_seo": True,  # Trigger scraper → SEO agent delegation
    }

    print("\n[DELEGATING] to scraper_agent (will auto-delegate to seo_agent)...")
    scraper_artifact = await orchestrator.delegate(
        "scraper_agent",
        ctx,
    )

    print(f"\n[SCRAPER RESULT]")
    print(f"  Status: {scraper_artifact.status}")
    print(f"  URL: {scraper_artifact.data.get('url')}")

    if seo_analysis := scraper_artifact.data.get("seo_analysis"):
        print(f"\n[SEO ANALYSIS] (delegated from scraper_agent)")
        print(f"  Meta title: {seo_analysis.get('meta_tags', {}).get('title')}")
        print(f"  Structured data types: {list(seo_analysis.get('structured_data', {}).keys())}")

    print(f"\n[SUB-ARTIFACTS]")
    for sub in scraper_artifact.sub_artifacts:
        print(f"  - {sub.agent_name}: {sub.status}")

    summary = orchestrator.get_usage_summary()
    print(f"\n[USAGE] Credits used: {summary['credits_used']}")
    print(f"[CALL CHAIN]")
    for call in summary['call_history']:
        indent = "  " if call['requested_by'] else ""
        print(f"{indent}→ {call['agent']} ({call['cost']} credits)")


# ============================================================================
# Example 5: Out of Credits Handling
# ============================================================================

async def example_out_of_credits():
    """Example: What happens when credits run out."""
    print("\n" + "=" * 80)
    print("Example 5: Out of Credits Handling")
    print("=" * 80)

    # Create orchestrator with very low credits
    orchestrator = AgentOrchestrator(
        phone_number="+15556667777",
        mode=AgentMode.SEMI_AUTONOMOUS,
        credits=10,  # Not enough for build_agent (50 credits)
    )

    ctx = {
        "phone_number": "+15556667777",
        "business_name": "Test Business",
        "build_type": "app",
    }

    print(f"\n[CREDITS] Starting with {orchestrator.credits_remaining} credits")
    print("[DELEGATING] to build_agent (costs 50 credits)...")

    build_artifact = await orchestrator.delegate(
        "build_agent",
        ctx,
    )

    print(f"\n[RESULT]")
    print(f"  Status: {build_artifact.status}")
    print(f"  Error: {build_artifact.metadata.get('error')}")

    summary = orchestrator.get_usage_summary()
    print(f"\n[USAGE]")
    print(f"  Credits remaining: {summary['credits_remaining']}")
    print(f"  Calls blocked: 1")


# ============================================================================
# Run all examples
# ============================================================================

async def main():
    """Run all examples."""
    # Example 1: Semi-autonomous with approvals
    await example_semi_autonomous_build()

    # Example 2: Fully autonomous (no approvals)
    await example_fully_autonomous_build()

    # Example 3: SEO agent standalone
    await example_seo_only()

    # Example 4: Agent chaining (scraper → SEO)
    await example_competitor_analysis()

    # Example 5: Out of credits
    await example_out_of_credits()

    print("\n" + "=" * 80)
    print("All examples complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
