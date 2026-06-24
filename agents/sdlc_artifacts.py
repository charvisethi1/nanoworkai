"""
SDLC Artifacts — typed data contracts passed between pipeline phases.

Each phase consumes the previous phase's artifact and produces its own.
This makes the pipeline explicit, testable, and easy to resume from any point.

Flow:
  RequirementsSpec → ArchitectureSpec → BuildArtifact → TestArtifact → ReleaseArtifact
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RequirementsSpec:
    """
    Phase 1 output: formalized requirements derived from user conversations.
    Everything downstream is driven by this artifact — not the raw ctx dict.
    """
    business_name: str
    tagline: str
    problem: str
    solution: str
    audience: str
    differentiator: str
    tone: str
    build_type: str
    pages: list[str]
    pricing_model: str
    pricing_details: str
    functional_requirements: list[str]  # human-readable list of what must be built
    ctx: dict = field(repr=False)       # raw ctx preserved for backward compat with existing agents
    # Set immediately after Phase 1 via reserve_project_slug RPC.
    # When set, release_phase uses this instead of generating a UUID-suffixed slug.
    reserved_slug: str | None = None
    # Company-specific SEO metadata generated alongside slug reservation.
    seo_metadata: dict = field(default_factory=dict)


@dataclass
class ArchitectureSpec:
    """
    Phase 2 output: visual design tokens + navigation structure.
    design_blueprint is the shared styling dict (field name kept for compatibility).
    site_plan defines pages and inter-page button connections.
    """
    requirements: RequirementsSpec
    design_blueprint: dict   # keys: design_style, brand_color, hero_layout, tone, nav_items, ...
    site_plan: dict          # keys: pages, page_plans (from plan_website)

    @property
    def enriched_ctx(self) -> dict:
        """Returns ctx merged with design tokens — what page builders expect."""
        return {**self.requirements.ctx, **self.design_blueprint}


@dataclass
class PageBuildResult:
    """Result of building one page in the development phase."""
    page: str
    jsx: str | None       # None if build failed
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.jsx is not None


@dataclass
class BuildArtifact:
    """
    Phase 3 output: raw (unvalidated) JSX per page.
    Pages are built in parallel; failed pages are recorded but don't block the pipeline.
    """
    architecture: ArchitectureSpec
    results: list[PageBuildResult]

    @property
    def successful_pages(self) -> dict[str, str]:
        return {r.page: r.jsx for r in self.results if r.succeeded}

    @property
    def failed_pages(self) -> list[str]:
        return [r.page for r in self.results if not r.succeeded]


@dataclass
class PageTestResult:
    """
    Result of validating one page in the testing phase.

    `passed` reflects the SYNTAX/runtime gate (precheck clean after fixes) —
    that's what blocks release.
    """
    page: str
    jsx: str              # validated (and possibly fixed) JSX
    issues_found: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass
class TestArtifact:
    """
    Phase 4 output: validated JSX per page + per-page test reports.
    All pages that passed testing are ready for assembly.
    """
    build: BuildArtifact
    results: list[PageTestResult]

    @property
    def page_jsxes(self) -> dict[str, str]:
        return {r.page: r.jsx for r in self.results}

    @property
    def failed_pages(self) -> list[str]:
        return [r.page for r in self.results if not r.passed]


@dataclass
class ReleaseArtifact:
    """Phase 5 output: the deployed site."""
    url: str
    slug: str
    pages_deployed: list[str]
    github_repo_url: str | None = None
