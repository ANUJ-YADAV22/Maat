"""Matplotlib figures. Every figure states that users are simulated and which backend ran."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BG, FG, GRID = "#0b0d14", "#e8eaf2", "#2a2f3f"
COLORS = {
    "S0": "#8b93a8",
    "S1": "#ff6173",
    "S2": "#ffb54a",
    "S3": "#c9a3ff",
    "S4": "#7aa2ff",
    "S5": "#e9bd57",
}


def _style(ax: Any, title: str, xl: str, yl: str) -> None:
    ax.set_facecolor(BG)
    ax.set_title(title, color=FG, fontsize=13, loc="left", pad=12)
    ax.set_xlabel(xl, color=FG)
    ax.set_ylabel(yl, color=FG)
    ax.tick_params(colors=FG)
    ax.grid(color=GRID, alpha=0.6, linewidth=0.7)
    for s in ax.spines.values():
        s.set_color(GRID)


def _fig(note: str) -> tuple[Any, Any]:
    fig, ax = plt.subplots(figsize=(9.5, 5.4), dpi=150, facecolor=BG)
    fig.text(0.01, 0.01, note, color="#8b93a8", fontsize=8)
    return fig, ax


def improvement_curve(
    path: Path,
    rounds: list[int],
    series: dict[str, dict[str, list[float]]],
    names: dict[str, str],
    note: str,
) -> None:
    fig, ax = _fig(note)
    for sid, s in series.items():
        m, se = s["mean"], s["se"]
        ax.plot(
            rounds,
            m,
            color=COLORS.get(sid),
            lw=3 if sid == "S5" else 1.8,
            label=f"{sid} {names.get(sid, '')}",
        )
        ax.fill_between(
            rounds,
            [a - b for a, b in zip(m, se, strict=True)],
            [a + b for a, b in zip(m, se, strict=True)],
            color=COLORS.get(sid),
            alpha=0.15,
        )
    _style(
        ax,
        "Held-out success vs feedback rounds (adversarial users)",
        "feedback round",
        "held-out success rate",
    )
    ax.set_ylim(0, 1.02)
    leg = ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9)
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def ablation(path: Path, rows: list[tuple[str, float, float, float, float]], note: str) -> None:
    """rows: (name, success mean, success se, bad-acceptance mean, bad-acceptance se)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.2), dpi=150, facecolor=BG, sharey=True)
    fig.text(0.01, 0.01, note, color="#8b93a8", fontsize=8)
    names = [r[0] for r in rows][::-1]
    y = range(len(rows))
    cols = [COLORS["S5"] if r[0].startswith("Full") else "#7aa2ff" for r in rows][::-1]
    a1.barh(y, [r[1] for r in rows][::-1], xerr=[r[2] for r in rows][::-1], color=cols, ecolor=FG)
    a2.barh(
        y, [r[3] for r in rows][::-1], xerr=[r[4] for r in rows][::-1], color="#ff6173", ecolor=FG
    )
    for ax, t, xl in (
        (a1, "Final held-out success", "success rate"),
        (a2, "Bad-patch acceptance", "fraction of bad patches adopted"),
    ):
        _style(ax, t, xl, "")
        ax.set_xlim(0, 1.02)
    a1.set_yticks(list(y))
    a1.set_yticklabels(names, color=FG)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def far_frr(path: Path, pts: list[dict[str, float]], note: str) -> None:
    fig, ax = _fig(note)
    if pts:
        t = [p["threshold"] for p in pts]
        ax.plot(
            t,
            [p["far"] for p in pts],
            color="#ff6173",
            lw=2.4,
            label="false accept (bad patches adopted)",
        )
        ax.plot(
            t,
            [p["frr"] for p in pts],
            color="#7aa2ff",
            lw=2.4,
            label="false reject (good patches blocked)",
        )
        ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG)
    else:
        ax.text(
            0.5,
            0.5,
            "no patch reached the statistical decision",
            color=FG,
            ha="center",
            transform=ax.transAxes,
        )
    _style(
        ax,
        "False accept vs false reject: decision-margin sweep (full gate)",
        "required margin (score minus bar)",
        "rate",
    )
    ax.set_ylim(0, 1.02)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
