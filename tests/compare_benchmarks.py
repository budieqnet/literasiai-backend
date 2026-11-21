"""
tests/compare_benchmarks.py
Bandingkan dua file hasil benchmark (mis. baseline 1 key vs run multi-key).

Jalankan:
    python tests/compare_benchmarks.py
    python tests/compare_benchmarks.py baseline.json candidate.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _model_rows(report: dict) -> dict:
    rows = dict(report.get("models") or {})
    if "fallback" in report:
        rows["keyword-fallback"] = report["fallback"]
    return rows


def compare_model(name: str, baseline: dict, candidate: dict) -> None:
    sa = baseline["summary"]
    sb = candidate["summary"]

    print("\n" + "=" * 96)
    print(f"MODEL: {name}")
    print("=" * 96)
    header = f"{'Metrik':<24} {'Baseline':>18} {'Run baru':>18} {'Delta':>14}"
    print(header)
    print("-" * len(header))

    def row(label: str, a, b, delta: str) -> None:
        print(f"{label:<24} {str(a):>18} {str(b):>18} {delta:>14}")

    row("Benar", f"{sa['correct']}/{sa['total']}", f"{sb['correct']}/{sb['total']}",
        f"{sb['correct'] - sa['correct']:+d}")
    row("Akurasi evaluated", _fmt_pct(sa["accuracy_evaluated"]), _fmt_pct(sb["accuracy_evaluated"]),
        f"{(sb['accuracy_evaluated'] - sa['accuracy_evaluated']) * 100:+.2f} pp")
    row("Akurasi end-to-end", _fmt_pct(sa["accuracy_all"]), _fmt_pct(sb["accuracy_all"]),
        f"{(sb['accuracy_all'] - sa['accuracy_all']) * 100:+.2f} pp")
    row("Error API", sa["errors"], sb["errors"], f"{sb['errors'] - sa['errors']:+d}")

    la = sa.get("latency") or {}
    lb = sb.get("latency") or {}
    for key in ("avg", "median", "p95", "max"):
        row(f"Latency {key}", f"{la.get(key, 0):.2f}s", f"{lb.get(key, 0):.2f}s",
            f"{lb.get(key, 0) - la.get(key, 0):+.2f}s")

    ra = {item["id"]: item for item in baseline["results"]}
    rb = {item["id"]: item for item in candidate["results"]}
    common = sorted(set(ra) & set(rb))
    improved = [rid for rid in common if not ra[rid]["correct"] and rb[rid]["correct"]]
    regressed = [rid for rid in common if ra[rid]["correct"] and not rb[rid]["correct"]]
    still_wrong = [rid for rid in common if not ra[rid]["correct"] and not rb[rid]["correct"]]
    stable_correct = [rid for rid in common if ra[rid]["correct"] and rb[rid]["correct"]]

    print(f"\nPer sampel (id sama): {len(common)}")
    print(f"  Tetap benar : {len(stable_correct)}")
    print(f"  Membaik    : {len(improved)} {improved if improved else ''}")
    print(f"  Memburuk   : {len(regressed)} {regressed if regressed else ''}")
    print(f"  Tetap salah: {len(still_wrong)} {still_wrong if still_wrong else ''}")

    if improved or regressed:
        for label, ids in (("MEMBAIK", improved), ("MEMBURUK", regressed)):
            for rid in ids:
                print(
                    f"  {label:8} {rid:8} expected={ra[rid]['expected']:<26} "
                    f"{ra[rid]['predicted'] or 'ERROR':<26} -> {rb[rid]['predicted'] or 'ERROR'}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bandingkan dua hasil benchmark")
    parser.add_argument(
        "baseline", nargs="?", type=Path,
        default=ROOT / "tests" / "data" / "benchmark_results.json",
    )
    parser.add_argument(
        "candidate", nargs="?", type=Path,
        default=ROOT / "tests" / "data" / "benchmark_results_2keys.json",
    )
    args = parser.parse_args()

    baseline = load(args.baseline)
    candidate = load(args.candidate)

    print("=" * 96)
    print("PERBANDINGAN BENCHMARK")
    print("=" * 96)
    print(f"Baseline : {args.baseline} ({baseline.get('timestamp', '?')})")
    print(f"Run baru : {args.candidate} ({candidate.get('timestamp', '?')})")
    print(f"Key      : {baseline.get('settings', {}).get('api_keys', '?')} -> "
          f"{candidate.get('settings', {}).get('api_keys', '?')}")

    rows_a = _model_rows(baseline)
    rows_b = _model_rows(candidate)
    for name in rows_a:
        if name in rows_b:
            compare_model(name, rows_a[name], rows_b[name])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
