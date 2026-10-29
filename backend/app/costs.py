"""Budget tracking and spend guards (Milestone 4 cost control).

Spend is accumulated in the `cost_log` table (see crud.add_cost). A project's
`monthly_budget_cap` of 0 means "no cap / unlimited". Any paid provider call
(Gemini tokens, Veo seconds) should estimate its cost, call `require_budget`
before spending, and log the actual amount after with crud.add_cost.
"""

from __future__ import annotations

from . import crud

# Rough public list price for Veo generation, USD per second of output video.
# An estimate for budgeting only — override with the VEO_PRICE_PER_SEC secret/env
# once the exact price for your model/tier is known.
DEFAULT_VEO_PRICE_PER_SEC = 0.40


class BudgetError(RuntimeError):
    """Raised (user-facing) when an action would exceed the project budget."""


def veo_price_per_sec() -> float:
    from .config import get_secret

    raw = get_secret("VEO_PRICE_PER_SEC")
    try:
        return float(raw) if raw else DEFAULT_VEO_PRICE_PER_SEC
    except (TypeError, ValueError):
        return DEFAULT_VEO_PRICE_PER_SEC


def estimate_veo_cost(seconds: float) -> float:
    return max(0.0, float(seconds)) * veo_price_per_sec()


def status(project: dict) -> dict:
    """Spend summary for a project, safe to expose to the UI."""
    total = crud.project_cost_total(project["id"])
    cap = float(project.get("monthly_budget_cap") or 0)
    return {
        "spent": round(total, 4),
        "cap": cap,
        "remaining": round(max(cap - total, 0.0), 4) if cap > 0 else None,
        "over": bool(cap > 0 and total >= cap),
    }


def require_budget(project: dict, estimated: float) -> None:
    """Raise BudgetError if spending `estimated` more would break the cap."""
    cap = float(project.get("monthly_budget_cap") or 0)
    if cap <= 0:
        return  # no cap configured = unlimited
    total = crud.project_cost_total(project["id"])
    if total + estimated > cap + 1e-9:
        raise BudgetError(
            f"This would cost about ${estimated:.2f} and the project has "
            f"${max(cap - total, 0.0):.2f} left of its ${cap:.2f} budget cap. "
            "Raise the cap in project settings or lower it to 0 for no cap."
        )
