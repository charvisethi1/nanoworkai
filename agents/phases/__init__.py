"""SDLC phase agents — one module per pipeline phase."""
from .requirements_phase import gather_requirements
from .architecture_phase import design_architecture
from .development_phase import build_pages
from .testing_phase import run_tests
from .release_phase import deploy
from .maintenance_phase import apply_patch

__all__ = [
    "gather_requirements",
    "design_architecture",
    "build_pages",
    "run_tests",
    "deploy",
    "apply_patch",
]
