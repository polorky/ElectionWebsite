from django.core.management.base import BaseCommand
from django.db.models import Sum

from uk_elections.models import Election, CandidateResult


class Command(BaseCommand):
    help = 'Backfill turnout_votes on pre-1833 by-elections from their CandidateResults.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would change without saving.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        elections = (
            Election.objects
            .filter(type='BE', date__year__lt=1833)
            .order_by('date')
        )

        updated = skipped_unopposed = skipped_no_votes = already_set = 0

        for elec in elections:
            crs = CandidateResult.objects.filter(election=elec)

            if crs.filter(unopposed=True).exists():
                self.stdout.write(f'  SKIP (unopposed): {elec}')
                skipped_unopposed += 1
                continue

            total = crs.aggregate(total=Sum('votes'))['total'] or 0

            if not total:
                self.stdout.write(f'  SKIP (no votes):  {elec}')
                skipped_no_votes += 1
                continue

            if elec.turnout_votes:
                self.stdout.write(f'  SKIP (already {elec.turnout_votes}): {elec}')
                already_set += 1
                continue

            self.stdout.write(f'  {"DRY " if dry_run else ""}SET {total} votes → {elec}')
            if not dry_run:
                elec.turnout_votes = total
                elec.save(update_fields=['turnout_votes'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. updated={updated}, skipped_unopposed={skipped_unopposed}, '
            f'skipped_no_votes={skipped_no_votes}, already_set={already_set}'
        ))
