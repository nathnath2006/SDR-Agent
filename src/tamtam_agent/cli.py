"""Point d'entrée : `tamtam-agent run` (ou `python -m tamtam_agent run`)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from . import agent, config, outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tamtam-agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Traiter un export et écrire les livrables")
    run.add_argument("--data", type=Path, default=Path("data/mirakl_case_data.xlsx"))
    run.add_argument("--out", type=Path, default=Path("outputs"))
    run.add_argument("--provider", default="auto", choices=["auto", "anthropic", "gemini", "none"],
                     help="auto : fournisseur des réglages (.env), sinon la clé disponible ; none : aucun texte rédigé")
    run.add_argument("--no-web", action="store_true", help="Sans vérification web de la présélection")
    run.add_argument("--top", type=int, default=config.TOP_N)
    run.add_argument("--cache", type=Path, default=Path(".cache/llm"))
    run.add_argument("-v", "--verbose", action="store_true")
    serve = sub.add_parser("serve", help="Lancer l'interface web (API + front compilé)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    load_dotenv()
    if args.command == "serve":
        import uvicorn
        print(f"Interface : http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}")
        uvicorn.run("tamtam_agent.api:app", host=args.host, port=args.port)
        return 0
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    result = agent.run(args.data, args.out, provider=args.provider, web=not args.no_web,
                       top_n=args.top, cache_dir=args.cache)
    paths = outputs.write_all(result, args.out)

    counts = {}
    for a in result.accounts:
        counts[a["statut"]] = counts.get(a["statut"], 0) + 1
    print(f"Extraction du {result.extraction_date.date()} · LLM : {result.llm_label}")
    print(f"{len(result.accounts)} groupes : " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"Top : {len(result.top)} comptes (" + ", ".join(
        f"{sum(a['palier'] == t for a in result.top)} {t}" for t in ("A", "B", "C")) + ")")
    for name, path in paths.items():
        print(f"  {name:13} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
