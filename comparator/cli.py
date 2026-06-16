"""Command-line entry point (SPEC §5 / §6 ``cli.py``).

    compare --reference REF.pdf --candidate CAND.pdf --config config.yaml --out report/

Exit code is non-zero when any defect has ``status == "defect"`` (for CI gating).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config
from .pipeline import run_comparison, write_reports
from .report import has_defects


def run(reference: str, candidate: str, config_path: str, out_dir: str) -> int:
    config = Config.load(config_path)
    report = run_comparison(reference, candidate, config)
    json_path, html_path = write_reports(report, candidate, config, out_dir)

    m = report["meta"]
    if m.get("page_count_mismatch"):
        print(f"[warn] page count differs; compared first {m['pages_compared']} page(s).")
    print(f"Analyzed {m['pages_compared']} page(s): {m['total_defects']} finding(s) "
          f"({m['counts_by_status']['defect']} defect, {m['counts_by_status']['review']} review).")
    print(f"Report: {json_path} | {html_path}")
    return 1 if has_defects(report) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compare", description="Creo/CAD PDF text-fidelity comparator")
    parser.add_argument("--reference", required=True, help="Reference (correct) drawing PDF")
    parser.add_argument("--candidate", required=True, help="Candidate (Creo-exported) drawing PDF")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--out", default="report", help="Output directory")
    args = parser.parse_args(argv)
    return run(args.reference, args.candidate, args.config, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
