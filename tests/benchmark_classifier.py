"""
tests/benchmark_classifier.py
Benchmark model klasifikasi NVIDIA pada dataset berlabel.

Script ini MEMANGGIL API NVIDIA ASLI dan menghabiskan kuota free tier.
Jalankan sequential dengan jeda agar tidak kena rate limit.

Contoh:
    python tests/benchmark_classifier.py
    python tests/benchmark_classifier.py --limit 20 --delay 2
    python tests/benchmark_classifier.py \
        --models nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3.5-super-vl-120b-a12b \
        --output tests/data/benchmark_results.json

Output: tabel ringkas di terminal + file JSON berisi hasil per sampel,
akurasi per kategori, error, dan statistik latency.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:  # progress terlihat saat output diarahkan ke file
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:  # pragma: no cover - Python lama
    pass

from config import Config  # noqa: E402
from app.services.nvidia import (  # noqa: E402
    NvidiaClassifyError,
    _get_api_keys,
    cache_info,
    classify_document,
    clear_cache,
)
from app.routes.classify import _fallback_classify  # noqa: E402


DEFAULT_DATASET = ROOT / "tests" / "data" / "classifier_benchmark.json"
DEFAULT_MODELS = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
]


def load_dataset(path: Path) -> list:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    samples = data.get("samples") if isinstance(data, dict) else data
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"Dataset tidak valid atau kosong: {path}")

    for index, sample in enumerate(samples, start=1):
        for field in ("expected", "title"):
            if not sample.get(field):
                raise ValueError(f"Sampel #{index} tidak punya field '{field}'")
        sample.setdefault("id", f"sample-{index:03d}")
        sample.setdefault("abstract", "")
        sample.setdefault("difficulty", "unknown")
    return samples


def _percentile(values: list, pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _latency_stats(values: list) -> dict:
    if not values:
        return {"count": 0, "avg": 0.0, "median": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "avg": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def summarize(results: list) -> dict:
    latencies = [item["latency_s"] for item in results if not item.get("error")]
    evaluated = [item for item in results if not item.get("error")]
    correct = [item for item in evaluated if item.get("correct")]
    errors = [item for item in results if item.get("error")]

    categories = {}
    for item in results:
        bucket = categories.setdefault(
            item["expected"], {"total": 0, "evaluated": 0, "correct": 0, "errors": 0}
        )
        bucket["total"] += 1
        if item.get("error"):
            bucket["errors"] += 1
        else:
            bucket["evaluated"] += 1
            if item.get("correct"):
                bucket["correct"] += 1

    for bucket in categories.values():
        bucket["accuracy"] = round(
            bucket["correct"] / bucket["evaluated"], 4
        ) if bucket["evaluated"] else 0.0

    total = len(results)
    return {
        "total": total,
        "evaluated": len(evaluated),
        "correct": len(correct),
        "errors": len(errors),
        "accuracy_evaluated": round(len(correct) / len(evaluated), 4) if evaluated else 0.0,
        "accuracy_all": round(len(correct) / total, 4) if total else 0.0,
        "latency": _latency_stats(latencies),
        "per_category": dict(sorted(categories.items())),
    }


def evaluate_model(model: str, samples: list, delay: float,
                   max_consecutive_errors: int) -> dict:
    """Jalankan satu model pada semua sampel; cache dimatikan agar latency nyata."""
    previous_model = Config.NVIDIA_MODEL
    previous_cache = Config.NVIDIA_CACHE_ENABLED
    Config.NVIDIA_MODEL = model
    Config.NVIDIA_CACHE_ENABLED = False
    clear_cache()

    results = []
    consecutive_errors = 0
    stopped_early = False
    started = time.time()

    print(f"\n=== {model} ===")
    print(f"Sampel: {len(samples)} | jeda: {delay}s | cache: off")
    print("-" * 96)
    print(f"{'No':>4}  {'Status':<8} {'Detik':>7}  {'Expected':<28} {'Predicted':<28}")
    print("-" * 96)

    try:
        for index, sample in enumerate(samples, start=1):
            started_sample = time.time()
            prediction = None
            confidence = None
            keywords = []
            error = None

            try:
                prediction = classify_document(
                    title=sample["title"],
                    abstract=sample.get("abstract", ""),
                    authors=sample.get("authors") or [],
                    year=sample.get("year", ""),
                    source=sample.get("source", ""),
                    subjects=sample.get("subjects") or [],
                )
                confidence = prediction.get("confidence")
                keywords = prediction.get("keywords") or []
                prediction = prediction.get("category")
            except NvidiaClassifyError as exc:
                error = str(exc)[:500]
            except Exception as exc:  # noqa: BLE001 - benchmark tidak boleh mati
                error = f"{type(exc).__name__}: {exc}"[:500]

            elapsed = time.time() - started_sample
            correct = bool(prediction) and prediction == sample["expected"]

            if error:
                consecutive_errors += 1
            else:
                consecutive_errors = 0

            results.append({
                "id": sample["id"],
                "expected": sample["expected"],
                "predicted": prediction,
                "correct": correct,
                "confidence": confidence,
                "keywords": keywords,
                "error": error,
                "latency_s": round(elapsed, 3),
                "difficulty": sample.get("difficulty", "unknown"),
            })

            status = "OK" if correct else ("ERROR" if error else "SALAH")
            shown_prediction = prediction or (error or "")[:26]
            print(
                f"{index:>4}  {status:<8} {elapsed:>7.2f}  "
                f"{sample['expected'][:28]:<28} {shown_prediction[:28]:<28}"
            )

            if consecutive_errors >= max_consecutive_errors:
                print(
                    f"\n! Berhenti lebih awal: {consecutive_errors} error beruntun. "
                    "Kemungkinan kuota/rate limit atau model tidak tersedia."
                )
                stopped_early = True
                break

            if index < len(samples) and delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\n! Dibatalkan pengguna; menyimpan hasil parsial.")
        stopped_early = True

    summary = summarize(results)
    summary["stopped_early"] = stopped_early
    summary["elapsed_s"] = round(time.time() - started, 2)
    summary["model"] = model
    summary["cache"] = cache_info()

    Config.NVIDIA_MODEL = previous_model
    Config.NVIDIA_CACHE_ENABLED = previous_cache
    clear_cache()

    return {"summary": summary, "results": results}


def evaluate_fallback(samples: list) -> dict:
    results = []
    started = time.time()
    for sample in samples:
        started_sample = time.time()
        output = _fallback_classify(
            sample["title"], sample.get("abstract", ""), sample.get("subjects") or []
        )
        elapsed = time.time() - started_sample
        predicted = output.get("category")
        results.append({
            "id": sample["id"],
            "expected": sample["expected"],
            "predicted": predicted,
            "correct": predicted == sample["expected"],
            "confidence": output.get("confidence"),
            "keywords": output.get("keywords") or [],
            "error": None,
            "latency_s": round(elapsed, 3),
            "difficulty": sample.get("difficulty", "unknown"),
        })

    summary = summarize(results)
    summary["elapsed_s"] = round(time.time() - started, 2)
    summary["model"] = "keyword-fallback"
    return {"summary": summary, "results": results}


def print_summary(name: str, summary: dict) -> None:
    latency = summary.get("latency") or {}
    print("\n" + "=" * 96)
    print(f"RINGKASAN — {name}")
    print("=" * 96)
    print(f"  Sampel            : {summary['total']}")
    print(f"  Evaluated         : {summary['evaluated']}")
    print(f"  Benar             : {summary['correct']}")
    print(f"  Error API         : {summary['errors']}")
    print(f"  Akurasi evaluated : {summary['accuracy_evaluated'] * 100:.2f}%")
    print(f"  Akurasi end-to-end: {summary['accuracy_all'] * 100:.2f}% (error dihitung salah)")
    print(
        "  Latency           : "
        f"avg {latency.get('avg', 0):.2f}s | median {latency.get('median', 0):.2f}s | "
        f"p95 {latency.get('p95', 0):.2f}s | max {latency.get('max', 0):.2f}s"
    )
    print(f"  Total waktu       : {summary.get('elapsed_s', 0):.1f}s")
    if summary.get("stopped_early"):
        print("  Catatan           : berhenti lebih awal (error beruntun / dibatalkan)")

    bad = [
        (category, stats)
        for category, stats in summary["per_category"].items()
        if stats["correct"] < stats["total"]
    ]
    if bad:
        print("\n  Kategori dengan kesalahan:")
        for category, stats in bad:
            print(
                f"    - {category:<28} {stats['correct']}/{stats['total']} benar "
                f"({stats['errors']} error API)"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark classifier NVIDIA LiterasiAI")
    parser.add_argument(
        "--dataset", type=Path, default=DEFAULT_DATASET,
        help=f"Path dataset JSON (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--models", default=",".join(DEFAULT_MODELS),
        help="Daftar model dipisah koma",
    )
    parser.add_argument("--limit", type=int, default=0, help="Batasi jumlah sampel (0 = semua)")
    parser.add_argument("--delay", type=float, default=1.2, help="Jeda antar request (detik)")
    parser.add_argument(
        "--max-consecutive-errors", type=int, default=5,
        help="Berhenti bila error beruntun mencapai jumlah ini (default: 5)",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "tests" / "data" / "benchmark_results.json",
        help="Path output JSON",
    )
    parser.add_argument("--no-fallback", action="store_true", help="Jangan evaluasi keyword fallback")
    parser.add_argument("--quiet", action="store_true", help="Hanya cetak ringkasan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = load_dataset(args.dataset)
    if args.limit > 0:
        samples = samples[: args.limit]

    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        print("Tidak ada model yang dipilih.")
        return 2

    print("=" * 96)
    print("  LiterasiAI — Benchmark Klasifikasi")
    print("=" * 96)
    print(f"  Dataset : {args.dataset} ({len(samples)} sampel)")
    print(f"  Model   : {', '.join(models)}")
    print(f"  Base URL: {Config.NVIDIA_BASE_URL}")
    print(f"  API keys: {len(_get_api_keys())}")
    print(f"  Timeout : {Config.NVIDIA_TIMEOUT}s | retries: {Config.NVIDIA_MAX_RETRIES}")
    print(f"  Jeda    : {args.delay}s | cache: off (latency nyata)")

    report = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dataset": {
            "path": str(args.dataset),
            "samples": len(samples),
            "categories": len({sample["expected"] for sample in samples}),
        },
        "settings": {
            "base_url": Config.NVIDIA_BASE_URL,
            "api_keys": len(_get_api_keys()),
            "timeout": Config.NVIDIA_TIMEOUT,
            "max_retries": Config.NVIDIA_MAX_RETRIES,
            "delay_s": args.delay,
            "cache_enabled": False,
        },
        "models": {},
    }

    for model in models:
        outcome = evaluate_model(
            model, samples, args.delay, args.max_consecutive_errors
        )
        report["models"][model] = outcome
        if not args.quiet:
            print_summary(model, outcome["summary"])

    if not args.no_fallback:
        fallback = evaluate_fallback(samples)
        report["fallback"] = fallback
        print_summary("keyword-fallback", fallback["summary"])

    print("\n" + "=" * 96)
    print("PERBANDINGAN")
    print("=" * 96)
    header = f"{'Model':<46} {'Benar':>7} {'Akurasi':>9} {'Error':>6} {'Avg':>7} {'P95':>7}"
    print(header)
    print("-" * len(header))
    rows = [(model, data["summary"]) for model, data in report["models"].items()]
    if "fallback" in report:
        rows.append(("keyword-fallback", report["fallback"]["summary"]))
    for name, summary in rows:
        latency = summary.get("latency") or {}
        print(
            f"{name[:46]:<46} "
            f"{summary['correct']:>3}/{summary['evaluated']:<3} "
            f"{summary['accuracy_evaluated'] * 100:>8.2f}% "
            f"{summary['errors']:>6} "
            f"{latency.get('avg', 0):>6.2f}s "
            f"{latency.get('p95', 0):>6.2f}s"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(f"\nHasil lengkap disimpan ke: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
