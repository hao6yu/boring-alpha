#!/usr/bin/env python3
"""Render BA-010 account paths from verified daily ledgers, without reading bars."""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


def render(report_path):
    report_path = Path(report_path)
    report = json.loads(report_path.read_text())
    path = report_path.parent / "day-ledger.jsonl"
    if hashlib.sha256(path.read_bytes()).hexdigest() != report["artifacts"][path.name]["sha256"]:
        raise ValueError("Daily ledger differs from report hash")
    models = defaultdict(list)
    for line in path.read_text().splitlines():
        row = json.loads(line)
        models[row["model"]].append(row)
    colors = {"base_pilot": "#175f9c", "stress_pilot": "#c47723", "base_unconstrained": "#727c85"}
    labels = {"base_pilot": "Pilot with capital and loss limits", "stress_pilot": "Pilot with double slippage",
              "base_unconstrained": "One-contract diagnostic, limits ignored"}
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [2, 1]}, layout="constrained")
        start = datetime(report["years"][0], 1, 1)
        for name in colors:
            rows = models[name]
            dates = [start] + [datetime.fromisoformat(r["date"]) for r in rows]
            equity = [5000] + [r["equity_end_cents"] / 100 for r in rows]
            style = "--" if name == "base_unconstrained" else "-"
            axes[0].plot(dates, equity, label=labels[name], color=colors[name], linestyle=style, lw=1.6)
            peak, drawdowns = 5000, []
            for value in equity:
                peak = max(peak, value)
                drawdowns.append(value - peak)
            axes[1].plot(dates, drawdowns, color=colors[name], linestyle=style, lw=1.3)
        rows = models["base_pilot"]
        dates = [start] + [datetime.fromisoformat(r["date"]) for r in rows]
        cash = [5000 * 1.06 ** ((d-start).days/365.2425) for d in dates]
        axes[0].plot(dates, cash, color="#43896f", lw=1.4, label="6% cash comparator")
        axes[0].axhline(4240, color="#aaa", linestyle=":", lw=1)
        halt = report["models"]["base_pilot"]["halt"]
        if halt:
            hday = datetime.fromisoformat(halt["date"])
            hvalue = halt["equity_cents"] / 100
            label = "Capital floor reached" if halt["reason"] == "capital_floor" else "$1,000 trailing drawdown triggered"
            axes[0].annotate(label + "\n" + halt["date"], xy=(hday, hvalue), xytext=(12, 28), textcoords="offset points",
                             fontsize=9, arrowprops={"arrowstyle": "->", "color": colors["base_pilot"]})
        axes[0].set_ylabel("Account equity (USD)")
        axes[0].legend(loc="best", fontsize=9)
        axes[1].axhline(-1000, color="#ad4b46", linestyle=":", lw=1)
        axes[1].set_ylabel("Daily closing drawdown (USD)")
        axes[1].xaxis.set_major_locator(mdates.YearLocator())
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for ax in axes:
            ax.grid(True, alpha=.16)
        stage = "Development" if report["stage"] == "development" else "Chronological validation"
        fig.suptitle(f"BA-010 · MES opening-range breakout\n{stage}: {report['years'][0]}–{report['years'][-1]}", fontsize=15)
        fig.supxlabel("Daily closing paths; the loss control uses minute-close equity. Fills, slippage and margin are modeled.", fontsize=9)
        for suffix in ("png", "svg"):
            target = report_path.parent / ("overview." + suffix)
            fig.savefig(target, dpi=170, facecolor="white")
        plt.close(fig)
    return report_path.parent / "overview.png"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    print(render(parser.parse_args().report))
