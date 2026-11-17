"""Load the bundled customer and loan workbooks."""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from celery import shared_task
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction

from customers.models import Customer
from loans.models import Loan

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_CUSTOMER_COLUMNS = [
    "Customer ID",
    "First Name",
    "Last Name",
    "Phone Number",
    "Monthly Salary",
    "Approved Limit",
]
_LOAN_COLUMNS = [
    "Customer ID",
    "Loan ID",
    "Loan Amount",
    "Tenure",
    "Interest Rate",
    "Monthly payment",
    "EMIs paid on Time",
    "Date of Approval",
    "End Date",
]
# Excel's 1900 date system, matching the origin pandas uses for serials.
_EXCEL_ORIGIN = date(1899, 12, 30)


def ingest_customer_and_loan_data(data_dir: Path | None = None) -> dict:
    """
    Upsert the sample workbooks.

    Loan IDs come from the Loan ID column. The workbook reuses some of those
    IDs for different loans. The first row keeps the original ID. Each later
    row is stored under a stable ID above every workbook ID so the credit
    history is kept and a second ingest updates the same rows.
    """
    import pandas as pd

    directory = Path(data_dir) if data_dir is not None else DATA_DIR
    customer_path = directory / "customer_data.xlsx"
    loan_path = directory / "loan_data.xlsx"
    missing = [path.name for path in (customer_path, loan_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Sample workbook not found: {', '.join(missing)}")

    customers = pd.read_excel(customer_path)
    loans = pd.read_excel(loan_path)
    _require_columns(customers, _CUSTOMER_COLUMNS, customer_path.name)
    _require_columns(loans, _LOAN_COLUMNS, loan_path.name)

    summary = {
        "customers": 0,
        "loans": 0,
        "duplicate_loan_ids_kept": 0,
        "customer_rows_skipped": 0,
        "loan_rows_skipped": 0,
    }
    with transaction.atomic():
        for position, row in customers.iterrows():
            try:
                with transaction.atomic():
                    _upsert_customer(row)
                summary["customers"] += 1
            except (IntegrityError, ValueError, TypeError, InvalidOperation) as exc:
                summary["customer_rows_skipped"] += 1
                logger.warning(
                    "Skipped customer row %s (%s)", position, exc.__class__.__name__
                )

        max_loan_id = int(loans["Loan ID"].max())
        seen_loan_ids = set()
        for position, row in loans.iterrows():
            try:
                raw_id = _as_int(row["Loan ID"])
                if raw_id in seen_loan_ids:
                    loan_id = max_loan_id + int(position) + 1
                    summary["duplicate_loan_ids_kept"] += 1
                else:
                    loan_id = raw_id
                    seen_loan_ids.add(raw_id)
                with transaction.atomic():
                    _upsert_loan(row, loan_id)
                summary["loans"] += 1
            except (
                IntegrityError,
                ValueError,
                TypeError,
                InvalidOperation,
                Customer.DoesNotExist,
            ) as exc:
                summary["loan_rows_skipped"] += 1
                logger.warning("Skipped loan row %s (%s)", position, exc.__class__.__name__)

        _refresh_current_debt()
        _reset_sequences()

    logger.info("Sample ingest finished: %s", summary)
    return summary


def _require_columns(frame, columns, name):
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")


def _upsert_customer(row):
    age = row["Age"] if "Age" in row.index else None
    Customer.objects.update_or_create(
        customer_id=_as_int(row["Customer ID"]),
        defaults={
            "first_name": str(row["First Name"]).strip(),
            "last_name": str(row["Last Name"]).strip(),
            "age": None if _missing(age) else _as_int(age),
            "phone_number": _as_int(row["Phone Number"]),
            "monthly_salary": _as_int(row["Monthly Salary"]),
            "approved_limit": _as_int(row["Approved Limit"]),
            "current_debt": Decimal("0.00"),
        },
    )


def _upsert_loan(row, loan_id):
    customer = Customer.objects.get(customer_id=_as_int(row["Customer ID"]))
    start = _as_date(row["Date of Approval"])
    end = _as_date(row["End Date"])
    if start is None or end is None:
        raise ValueError("loan dates are missing")
    Loan.objects.update_or_create(
        loan_id=loan_id,
        defaults={
            "customer": customer,
            "loan_amount": _as_money(row["Loan Amount"]),
            "interest_rate": _as_money(row["Interest Rate"]),
            "tenure": _as_int(row["Tenure"]),
            "monthly_installment": _as_money(row["Monthly payment"]),
            "emis_paid_on_time": _as_int(row["EMIs paid on Time"]),
            "start_date": start,
            "end_date": end,
        },
    )


def _refresh_current_debt():
    from django.db.models import Sum
    from django.utils import timezone

    today = timezone.now().date()
    for customer in Customer.objects.all().iterator():
        total = customer.loans.filter(end_date__gt=today).aggregate(total=Sum("loan_amount"))
        customer.current_debt = total["total"] or Decimal("0.00")
        customer.save(update_fields=["current_debt"])


def _reset_sequences():
    statements = connection.ops.sequence_reset_sql(no_style(), [Customer, Loan])
    if not statements:
        return
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def _missing(value) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        result = pd.isna(value)
    except TypeError:
        return False
    return bool(result) if result is not None else False


def _as_int(value) -> int:
    if _missing(value):
        raise ValueError("missing integer")
    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise ValueError("expected an integer")
    return int(number)


def _as_money(value) -> Decimal:
    if _missing(value):
        raise ValueError("missing amount")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _as_date(value):
    if _missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _EXCEL_ORIGIN + timedelta(days=int(value))
    text = str(value).strip()
    if not text:
        return None
    from dateutil.parser import parse

    return parse(text).date()


@shared_task(ignore_result=True)
def ingest_initial_data():
    """Celery entry point. On Render this runs in-process when eager mode is on."""
    return ingest_customer_and_loan_data()
