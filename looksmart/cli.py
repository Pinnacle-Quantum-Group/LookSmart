"""LookSmart command-line interface.

Subcommands exercise the pipeline in DRY-RUN by default; sending traffic to a
live LLM account requires the explicit `--send` flag on a configured provider.
"""

from __future__ import annotations

import argparse
import sys

from .config import LookSmartConfig
from .models import GenerationMode, Session
from .orchestrator import Orchestrator


def _load_config(path: str | None) -> LookSmartConfig:
    return LookSmartConfig.load(path) if path else LookSmartConfig()


def cmd_init_config(args) -> int:
    LookSmartConfig().dump(args.path)
    print(f"wrote default config to {args.path}")
    return 0


def cmd_decoy(args) -> int:
    cfg = _load_config(args.config)
    orch = Orchestrator(cfg, seed=args.seed)
    try:
        mode = GenerationMode(args.mode) if args.mode else None
        for _ in range(args.n):
            item = orch.generate_decoy(mode=mode)
            sent = orch.dispatch(
                item, provider=args.provider, live=args.send,
            )
            if isinstance(item, Session):
                print(f"[decoy session: {item.mode.value if item.mode else '?'} "
                      f"persona={item.persona_id} turns={len(item.turns)}]")
                for t in item.turns:
                    print(f"  > {t.prompt}")
            else:
                print(f"[decoy: {item.mode.value if item.mode else '?'} "
                      f"persona={item.persona_id}] {item.text}")
            if sent is not None:
                print(f"  (sent to {args.provider})")
    finally:
        orch.close()
    return 0


def cmd_real(args) -> int:
    cfg = _load_config(args.config)
    orch = Orchestrator(cfg, seed=args.seed)
    try:
        q = orch.prepare_real(args.text, user_override_passthrough=args.no_inject)
        print(f"injection: {q.injection.injection_type.value if q.injection else 'none'}")
        print(f"sent text: {q.text}")
        assert q.original_text and q.original_text in q.text or q.original_text == q.text
        resp = orch.dispatch(q, provider=args.provider, live=args.send)
        if resp is not None:
            print(f"response ({args.provider}): {resp.text[:500]}")
        else:
            print("(dry-run: not transmitted; pass --send with a provider to send)")
    finally:
        orch.close()
    return 0


def cmd_audit_verify(args) -> int:
    cfg = _load_config(args.config)
    orch = Orchestrator(cfg, seed=args.seed)
    try:
        rows = orch.audit.verify(args.text)
        print(f"{len(rows)} decoy(s) logged as cover for that query:")
        for r in rows:
            print(f"  [{r['mode']}] persona={r['persona_id']}: {r['text']}")
    finally:
        orch.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="looksmart", description=__doc__)
    p.add_argument("--config", help="path to config YAML (defaults if omitted)")
    p.add_argument("--seed", type=int, default=None, help="RNG seed")
    sub = p.add_subparsers(dest="cmd", required=True)

    ic = sub.add_parser("init-config", help="write a default config file")
    ic.add_argument("path")
    ic.set_defaults(func=cmd_init_config)

    d = sub.add_parser("decoy", help="generate decoy traffic (dry-run by default)")
    d.add_argument("--mode", choices=[m.value for m in GenerationMode], default=None)
    d.add_argument("-n", type=int, default=3)
    d.add_argument("--provider", default=None)
    d.add_argument("--send", action="store_true", help="actually transmit (ToS, §7)")
    d.set_defaults(func=cmd_decoy)

    r = sub.add_parser("real", help="prepare/send a real query via CooKoo")
    r.add_argument("text")
    r.add_argument("--no-inject", action="store_true", help="force passthrough")
    r.add_argument("--provider", default=None)
    r.add_argument("--send", action="store_true", help="actually transmit (ToS, §7)")
    r.set_defaults(func=cmd_real)

    av = sub.add_parser("audit-verify", help="which decoys covered a real query")
    av.add_argument("text")
    av.set_defaults(func=cmd_audit_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
