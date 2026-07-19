"""python manage.py seed_data: load the seed parquet (idempotent).

--since / --days bound the load to recent effective dates (used to seed a light,
representative slice on a free-tier deploy). Omit both to load the full history.
"""

import datetime as dt
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rates.cache import invalidate_latest
from rates.ingestion import ingest
from rates.sources import SeedFileSource

log = logging.getLogger("rates.ingest")


class Command(BaseCommand):
    help = "Load rate data from the seed parquet into the database (idempotent)."

    def add_arguments(self, parser):
        default_path = Path(settings.BASE_DIR).parent / "data" / "rates_seed.parquet"
        parser.add_argument("--path", default=str(default_path), help="Path to the parquet file.")
        parser.add_argument("--batch-size", type=int, default=50_000, help="Rows per read batch.")
        parser.add_argument(
            "--since",
            default=None,
            help="Only load rows with effective_date >= this ISO date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Only load the last N days of effective dates (ignored if --since is given).",
        )

    def _resolve_since(self, options) -> dt.date | None:
        if options["since"]:
            try:
                return dt.date.fromisoformat(options["since"])
            except ValueError as exc:
                raise CommandError(f"Invalid --since '{options['since']}', expected YYYY-MM-DD.") from exc
        if options["days"] is not None:
            if options["days"] < 0:
                raise CommandError("--days must be zero or positive.")
            return timezone.localdate() - dt.timedelta(days=options["days"])
        return None

    def handle(self, *args, **options):
        since = self._resolve_since(options)
        source = SeedFileSource(options["path"], batch_size=options["batch_size"], since=since)
        stats = ingest(source)
        # Cache invalidation is best-effort: a seed shouldn't fail if the cache is
        # briefly unreachable (e.g. seeding a fresh deploy before Redis is wired).
        try:
            invalidate_latest()
        except Exception as exc:  # noqa: BLE001 - non-fatal cache bust
            log.warning("seed_cache_invalidation_failed", extra={"error": str(exc)})
        window = f" since={since}" if since else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"landed={stats.landed} promoted={stats.promoted} "
                f"rejected={dict(stats.rejected)}{window}"
            )
        )
