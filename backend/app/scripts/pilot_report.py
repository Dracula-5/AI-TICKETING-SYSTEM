"""
Write a pilot report for one organization (Markdown on stdout, JSON with --json).

    python -m app.scripts.pilot_report --org <slug> [--days 30] [--json]

Every figure is computed from the database by app/services/pilot.py. Demo and
synthetic organizations are labelled as such in the report.
"""

import argparse
import json
import sys

from app.db.database import SessionLocal
from app.db.models import Tenant
from app.services import pilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--org", required=True, help="organization slug")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == args.org).first()
        if tenant is None:
            print(f"No organization with slug {args.org!r}", file=sys.stderr)
            return 2
        metrics = pilot.compute(db, tenant, args.days)
    finally:
        db.close()
    print(json.dumps(metrics, indent=2) if args.json else pilot.to_markdown(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
