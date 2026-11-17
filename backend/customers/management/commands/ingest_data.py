import os

from django.core.management.base import BaseCommand, CommandError

from customers.models import Customer
from customers.tasks import ingest_customer_and_loan_data

_OFF = {"0", "false", "no", "off"}
_ALWAYS = {"1", "true", "yes", "on", "always"}


class Command(BaseCommand):
    help = (
        "Load data/customer_data.xlsx and data/loan_data.xlsx. "
        "SEED_ON_START=if-empty (default) skips when any customer exists. "
        "SEED_ON_START=always reloads the workbooks. SEED_ON_START=false skips."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reload the workbooks even when customers already exist.",
        )

    def handle(self, *args, **options):
        mode = os.environ.get("SEED_ON_START", "if-empty").strip().lower()
        if options["force"]:
            mode = "always"
        if mode in _OFF:
            self.stdout.write("Skipping sample ingest because SEED_ON_START is off.")
            return
        if mode not in _ALWAYS and Customer.objects.exists():
            self.stdout.write("Skipping sample ingest; customers already exist.")
            return
        try:
            summary = ingest_customer_and_loan_data()
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            "Ingested "
            f"customers={summary['customers']} "
            f"loans={summary['loans']} "
            f"duplicate_loan_ids_kept={summary['duplicate_loan_ids_kept']} "
            f"customer_rows_skipped={summary['customer_rows_skipped']} "
            f"loan_rows_skipped={summary['loan_rows_skipped']}"
        ))
