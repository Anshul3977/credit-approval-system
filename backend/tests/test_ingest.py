from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from customers.models import Customer
from customers.tasks import ingest_customer_and_loan_data, ingest_initial_data
from loans.models import Loan

from .factories import make_customer


def _workbook(path, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    book.save(path)


def _write_fixture(directory):
    _workbook(
        directory / "customer_data.xlsx",
        [
            "Customer ID",
            "First Name",
            "Last Name",
            "Age",
            "Phone Number",
            "Monthly Salary",
            "Approved Limit",
        ],
        [
            [5, "Ada", "Lovelace", 36, 9111111111, 80000, 2000000],
            [8, "Grace", "Hopper", 40, 9222222222, 90000, 3000000],
        ],
    )
    _workbook(
        directory / "loan_data.xlsx",
        [
            "Customer ID",
            "Loan ID",
            "Loan Amount",
            "Tenure",
            "Interest Rate",
            "Monthly payment",
            "EMIs paid on Time",
            "Date of Approval",
            "End Date",
        ],
        [
            [5, 4242, 50000, 12, 8.2, 4000, 6, datetime(2021, 5, 1), datetime(2022, 5, 1)],
            [8, 4242, 80000, 24, 11.5, 3500, 10, datetime(2024, 1, 1), datetime(2030, 1, 1)],
            [5, 7, 10000, 6, 9.25, 1800, 1, 44562, 44662],
        ],
    )


@pytest.mark.django_db
def test_ingest_keeps_workbook_ids_and_is_idempotent(tmp_path):
    _write_fixture(tmp_path)
    summary = ingest_customer_and_loan_data(tmp_path)
    assert summary["customers"] == 2
    assert summary["loans"] == 3
    assert summary["duplicate_loan_ids_kept"] == 1
    assert summary["loan_rows_skipped"] == 0

    original = Loan.objects.get(loan_id=4242)
    assert original.loan_amount == Decimal("50000.00")
    assert original.interest_rate == Decimal("8.2000")
    assert original.start_date == date(2021, 5, 1)
    amounts = set(Loan.objects.values_list("loan_amount", flat=True))
    assert Decimal("80000.00") in amounts
    serial = Loan.objects.get(loan_id=7)
    assert serial.start_date == date(2022, 1, 1)
    assert serial.end_date == date(2022, 4, 11)

    ada = Customer.objects.get(customer_id=5)
    assert ada.current_debt == Decimal("0.00")
    grace = Customer.objects.get(customer_id=8)
    assert grace.current_debt == Decimal("80000.00")

    again = ingest_customer_and_loan_data(tmp_path)
    assert again["loans"] == 3
    assert Loan.objects.count() == 3
    assert Customer.objects.count() == 2

    created = make_customer(phone_number=9333333333)
    assert created.customer_id == 9


@pytest.mark.django_db
def test_celery_task_runs_in_process_without_a_broker(tmp_path, monkeypatch):
    _write_fixture(tmp_path)
    monkeypatch.setattr("customers.tasks.DATA_DIR", tmp_path)
    from credit_system.celery import app

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    ingest_initial_data.delay()
    assert Customer.objects.filter(customer_id=5, first_name="Ada").exists()


@pytest.mark.django_db
def test_bundled_sample_workbook():
    """Counts and ids below are the bundled workbooks, not a live-traffic claim."""
    summary = ingest_customer_and_loan_data()
    assert summary == {
        "customers": 300,
        "loans": 782,
        "duplicate_loan_ids_kept": 29,
        "customer_rows_skipped": 0,
        "loan_rows_skipped": 0,
    }
    assert Customer.objects.count() == 300
    assert Loan.objects.count() == 782

    aaron = Customer.objects.get(customer_id=1)
    assert aaron.first_name == "Aaron"
    assert aaron.last_name == "Garcia"
    assert aaron.monthly_salary == 50000
    # The workbook value is kept. /register would calculate 1800000 for this salary.
    assert aaron.approved_limit == 4_500_000
    assert aaron.phone_number == 9629317944

    loan = Loan.objects.get(loan_id=5930)
    assert loan.customer_id == 14
    assert loan.loan_amount == Decimal("900000.00")
    assert loan.interest_rate == Decimal("8.2000")

    created = make_customer(phone_number=1000000001)
    assert created.customer_id == 301
