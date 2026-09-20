"""Create the schema, load the Olympic graph and install the agent's queries.

Usage:
    python scripts/load_tigergraph.py --schema --load --queries

Connection settings come from .env (see .env.example). Run with --dry-run to
print what would be sent without touching a cluster.
"""
import argparse

from dotenv import load_dotenv

from occam import context
from occam.store import tigergraph as tg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true", help="create vertices/edges")
    ap.add_argument("--vectors", action="store_true", help="add the Chunk vector attribute")
    ap.add_argument("--load", action="store_true", help="upsert events and edges")
    ap.add_argument("--queries", action="store_true", help="install the agent's GSQL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_dotenv()

    cfg = tg.TGConfig.from_env(require=not args.dry_run)
    ctx = context.load(with_index=False)
    print(f"  graph '{cfg.graph}' at {cfg.host}")

    if args.dry_run:
        if args.schema:
            print(tg.SCHEMA_GSQL.format(graph=cfg.graph))
        if args.vectors:
            print(tg.VECTOR_GSQL.format(graph=cfg.graph, dim=384))
        if args.queries:
            for name, q in tg.QUERIES_GSQL.items():
                print(f"\n-- {name} --{q.format(graph=cfg.graph)}")
        print(f"\n  would load {len(ctx.graph.events)} events")
        return

    conn = tg.connect(cfg)
    if args.schema:
        print(conn.gsql(tg.SCHEMA_GSQL.format(graph=cfg.graph)))
    if args.vectors:
        print(conn.gsql(tg.VECTOR_GSQL.format(graph=cfg.graph, dim=384)))
    if args.load:
        counts = tg.load_events(conn, ctx.graph.events)
        for k, v in counts.items():
            print(f"    {k:<14} {v:>7,}")
    if args.queries:
        for name, q in tg.QUERIES_GSQL.items():
            print(f"    installing {name}")
            conn.gsql(q.format(graph=cfg.graph))
        conn.gsql(f"USE GRAPH {cfg.graph}\nINSTALL QUERY ALL")
    print("  done")


if __name__ == "__main__":
    main()
