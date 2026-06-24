# Agent Architecture

## Overview

Nanowork uses a multi-agent orchestration system where specialized agents collaborate to build and optimize web applications. Agents can delegate work to other agents, with built-in usage tracking and approval flows for different autonomy levels.

## Agent Modes

### 1. Semi-Autonomous (Default)
- **Credits**: 100 credits (default allocation)
- **Behavior**: Agents can delegate to other agents, but require user approval
- **Use case**: Controlled experimentation, cost management
- **Upgrade**: User can add more credits or upgrade to fully autonomous

### 2. Fully Autonomous
- **Credits**: Unlimited or high limit (e.g., 10,000)
- **Behavior**: Agents freely delegate without approval
- **Use case**: Production workflows, power users
- **Cost**: Premium subscription tier

### 3. Manual
- **Credits**: N/A
- **Behavior**: No automatic agent delegation
- **Use case**: Traditional fixed pipeline (backward compatible)

## Agent Organization

```
src/nanowork_mobile/agents/
├── core/                    # Core orchestration & framework
│   ├── orchestration.py     # Multi-agent orchestrator
│   ├── registry.py          # Agent registry
│   └── artifacts.py         # Typed artifacts for agent communication
│
├── builders/                # App/site building agents
│   ├── build_agent.py       # Main build coordinator
│   ├── app_builder.py       # Functional app pipeline
│   ├── page_builder.py      # Page generation
│   ├── design_agent.py      # Brand imagery, design tokens
│   └── assembly_agent.py    # Multi-page assembly
│
├── optimizers/              # Post-build optimization agents
│   ├── seo_agent.py         # SEO optimization (meta, structured data, sitemap)
│   ├── performance_agent.py # Bundle size, lazy loading, CDN
│   └── a11y_agent.py        # Accessibility checks
│
├── analyzers/               # Data extraction & analysis agents
│   ├── scraper_agent.py     # Web scraping
│   ├── market_agent.py      # Market research
│   └── competitor_agent.py  # Competitor analysis
│
├── validators/              # Quality assurance agents
│   ├── syntax_agent.py      # JSX/HTML validation
│   ├── testing_agent.py     # E2E and unit tests
│   └── security_agent.py    # Security vulnerability scanning
│
├── legacy/                  # Deprecated agents (kept for backward compat)
│   ├── seo_agent_v1.py
│   ├── scraper_agent_v1.py
│   └── unified_business_agent.py
│
└── orchestrator_agent.py    # Legacy main orchestrator (being migrated)
```

## Agent Communication

### Artifacts (Preferred)

Agents communicate via typed `AgentArtifact` objects:

```python
@dataclass
class AgentArtifact:
    agent_name: str
    status: str  # "success" | "partial" | "failed"
    data: dict
    metadata: dict
    sub_artifacts: list[AgentArtifact]
```

**Benefits**:
- Type-safe
- Supports dependency tracking
- Can merge multiple artifacts
- Contains metadata (timing, costs, errors)

### Context Dict (Legacy)

Old agents pass enriched `ctx` dicts. Still supported but being migrated.

## Agent Delegation Example

```python
from nanowork_mobile.core.agents.orchestration import AgentOrchestrator, AgentMode

# Create orchestrator
orchestrator = AgentOrchestrator(
    phone_number="+15551234567",
    mode=AgentMode.SEMI_AUTONOMOUS,
    credits=100,
    approval_callback=ask_user_for_approval,
)

# Delegate to build agent
build_artifact = await orchestrator.delegate(
    "build_agent",
    {
        "business_name": "Coffee Shop",
        "description": "Local cafe app",
    },
)

# Build agent can delegate to other agents
# e.g., build_agent → seo_agent → structured_data_generator
```

## Agent Registration

Register agents using the `@register_agent` decorator:

```python
from nanowork_mobile.core.agents.orchestration import register_agent, AgentArtifact

@register_agent("my_agent", credits_cost=15)
async def my_agent(
    ctx: dict,
    orchestrator: Optional[AgentOrchestrator] = None,
) -> AgentArtifact:
    """
    My specialized agent.

    Can delegate to other agents via:
        artifact = await orchestrator.delegate("other_agent", {...})
    """
    # Do work
    result = do_something(ctx)

    # Optionally delegate to another agent
    if orchestrator and ctx.get("optimize_seo"):
        seo_artifact = await orchestrator.delegate(
            "seo_agent",
            {"html": result["html"]},
            requesting_agent="my_agent",
        )
        result["seo"] = seo_artifact.data

    return AgentArtifact(
        agent_name="my_agent",
        status="success",
        data=result,
    )
```

## Credit Costs

| Agent | Credits | Description |
|-------|---------|-------------|
| build_agent | 50 | Main build coordinator |
| seo_agent | 20 | Full SEO optimization |
| design_agent | 15 | Brand imagery generation |
| scraper_agent | 15 | Web scraping |
| syntax_agent | 5 | JSX validation |
| testing_agent | 10 | E2E tests |

## Database Schema

### `user_agent_plans`
Tracks per-user agent plans and credit balances:
```sql
- phone_number (PK)
- plan_type (semi_autonomous | fully_autonomous | manual)
- credits_total
- credits_used
- credits_remaining (generated)
- auto_recharge (boolean)
- recharge_threshold
- recharge_amount
```

### `agent_usage_logs`
Audit log of all agent invocations:
```sql
- id (UUID)
- phone_number
- mode
- credits_used
- total_calls
- call_history (JSONB)
- created_at
```

### `agent_approval_queue`
Approval requests for semi-autonomous mode:
```sql
- id (UUID)
- phone_number
- agent_name
- requesting_agent
- context (JSONB)
- credits_cost
- status (pending | approved | rejected | expired)
- expires_at (15 min default)
```

## Migration Path

### Phase 1: Core Framework ✅
- [x] `core/agents/orchestration.py` — orchestrator, registry, artifacts
- [x] `agents/seo_agent_v2.py` — full SEO optimization
- [x] `agents/scraper_agent_v2.py` — scraper with delegation
- [x] `agents/build_orchestrator.py` — build agent wrapper
- [x] Database migrations

### Phase 2: Reorganization (Next)
- [ ] Move agents into new folder structure
- [ ] Create `__init__.py` for each package
- [ ] Update imports across codebase
- [ ] Add package-level docs

### Phase 3: New Agents
- [ ] `optimizers/performance_agent.py`
- [ ] `optimizers/a11y_agent.py`
- [ ] `analyzers/competitor_agent.py`
- [ ] `validators/security_agent.py`

### Phase 4: Full Integration
- [ ] Replace `orchestrator_agent.py` calls with `build_orchestrator.py`
- [ ] Add approval UI for semi-autonomous mode
- [ ] Implement credit recharge webhooks
- [ ] Analytics dashboard for agent usage

## Testing

```bash
# Run agent tests
pytest tests/test_agent_orchestration.py

# Test specific agent
pytest tests/test_seo_agent_v2.py -v

# Test with different modes
pytest tests/test_agents.py --mode=semi_autonomous
pytest tests/test_agents.py --mode=fully_autonomous
```

## Future Enhancements

1. **Agent Learning**: Store successful agent chains in memory for pattern recognition
2. **Cost Optimization**: Dynamic credit pricing based on LLM model used
3. **Parallel Execution**: Run independent agents in parallel (e.g., scraper + design)
4. **Agent Marketplace**: Allow users to create and share custom agents
5. **Chain Templates**: Pre-defined agent chains for common workflows (e.g., "competitor_analysis" → scraper + seo + market_agent)
