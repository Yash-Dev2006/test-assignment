"""CLI: ingest/eval/segment/analyze."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def cmd_evaluate_a(args: argparse.Namespace) -> None:
    from src.evaluate_a import evaluate_dataset, grid_search, result_to_dict

    root = Path(args.root)
    if args.grid:
        results = grid_search(root)
        payload = [result_to_dict(r) for r in results]
        print(json.dumps({"best": payload[0], "grid": payload}, indent=2, ensure_ascii=False))
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"best": payload[0], "grid": payload}, indent=2), encoding="utf-8")
        return
    result = evaluate_dataset(root, debounce_ms=args.debounce_ms, idle_ms=args.idle_ms)
    payload = result_to_dict(result)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_segment_b(args: argparse.Namespace) -> None:
    from src.analyze_b import collect_segments, write_segments_jsonl

    segs = collect_segments(Path(args.root), debounce_ms=args.debounce_ms, idle_ms=args.idle_ms)
    out = Path(args.out)
    write_segments_jsonl(segs, out)
    n_kept = sum(1 for s in segs if s.label != "unrelated")
    print(json.dumps({"sessions_segments": len(segs), "written_non_unrelated": n_kept, "out": str(out)}))


def cmd_analyze_b(args: argparse.Namespace) -> None:
    from src.analyze_b import analyze, collect_segments, stats_to_dict, write_segments_jsonl

    segs = collect_segments(Path(args.root), debounce_ms=args.debounce_ms, idle_ms=args.idle_ms)
    if args.segments_out:
        write_segments_jsonl(segs, Path(args.segments_out))
    stats = analyze(segs)
    payload = {
        "n_segments": len(segs),
        "ranking": [stats_to_dict(s) for s in stats],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_inventory(args: argparse.Namespace) -> None:
    from collections import Counter
    from src.features import extract_event_features, annotate_with_carry_forward, process_key
    from src.ingest import iter_dataset_sessions

    keys = Counter()
    apps = Counter()
    n = 0
    for ses_id, _path, events in iter_dataset_sessions(Path(args.root)):
        feats = annotate_with_carry_forward([extract_event_features(e) for e in events])
        for f in feats:
            n += 1
            keys[process_key(f)] += 1
            if f.app_name:
                apps[f.app_name] += 1
    print(json.dumps({"events": n, "keys": keys.most_common(25), "apps": apps.most_common(12)}, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src")
    sub = p.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="Count process keys / apps")
    inv.add_argument("--root", required=True)
    inv.set_defaults(func=cmd_inventory)

    ev = sub.add_parser("evaluate-a", help="IoU eval on Dataset A")
    ev.add_argument("--root", default="dataset_a 2")
    ev.add_argument("--grid", action="store_true")
    ev.add_argument("--debounce-ms", type=int, default=4000)
    ev.add_argument("--idle-ms", type=int, default=90000)
    ev.add_argument("--out")
    ev.set_defaults(func=cmd_evaluate_a)

    sb = sub.add_parser("segment-b", help="Write Dataset B segments.jsonl")
    sb.add_argument("--root", default="dataset_b")
    sb.add_argument("--out", default="segments.jsonl")
    sb.add_argument("--debounce-ms", type=int, default=4000)
    sb.add_argument("--idle-ms", type=int, default=90000)
    sb.set_defaults(func=cmd_segment_b)

    ab = sub.add_parser("analyze-b", help="Rank processes for automation")
    ab.add_argument("--root", default="dataset_b")
    ab.add_argument("--out", default="artifacts/analysis_b.json")
    ab.add_argument("--segments-out")
    ab.add_argument("--debounce-ms", type=int, default=4000)
    ab.add_argument("--idle-ms", type=int, default=90000)
    ab.set_defaults(func=cmd_analyze_b)

    demo = sub.add_parser("demo", help="Generate memo/notes from case JSON")
    demo.add_argument("--input", default="automation/sample_cases.json")
    demo.add_argument("--out", default="automation/out")
    demo.set_defaults(func=cmd_demo)
    return p


def cmd_demo(args: argparse.Namespace) -> None:
    from src.automation.demo import main as demo_main

    demo_main(["--input", args.input, "--out", args.out])


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
