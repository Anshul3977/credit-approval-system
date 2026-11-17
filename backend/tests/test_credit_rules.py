from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from loans.utils import calculate_credit_score, calculate_emi

from .factories import make_customer, make_loan


def _history(customer, *, count, paid_ratio, this_year, amount=Decimal("0.00")):
    today = timezone.now().date()
    if this_year:
        start = date(today.year, 1, 1)
        end = start
    else:
        start = date(today.year - 1, 6, 1)
        end = date(today.year - 1, 7, 1)
    tenure = 40 if paid_ratio == Decimal("0.175") else 10
    emis_paid = int(paid_ratio * tenure)
    for _ in range(count):
        make_loan(
            customer,
            loan_amount=amount,
            tenure=tenure,
            emis_paid_on_time=emis_paid,
            start_date=start,
            end_date=end,
        )
    return customer


def _customer(kind):
    if kind == "new":
        return make_customer()
    customer = make_customer()
    if kind == "s51":
        return _history(customer, count=1, paid_ratio=Decimal("0.7"), this_year=False)
    if kind == "s31":
        return _history(customer, count=1, paid_ratio=Decimal("0.2"), this_year=False)
    if kind == "s30":
        return _history(customer, count=1, paid_ratio=Decimal("0.175"), this_year=False)
    if kind == "s11":
        return _history(customer, count=7, paid_ratio=Decimal("0"), this_year=True)
    if kind == "s10":
        return _history(customer, count=8, paid_ratio=Decimal("0"), this_year=True)
    if kind == "debt":
        customer.approved_limit = 1000
        customer.current_debt = Decimal("1001.00")
        customer.save(update_fields=["approved_limit", "current_debt"])
        make_loan(customer, loan_amount=Decimal("1.00"))
        return customer
    raise AssertionError(kind)


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "rate", "expected_score", "approved", "corrected"),
    [
        ("new", "11.99", 50, False, "12"),
        ("new", "12", 50, True, "12"),
        ("s51", "5", 51, True, "5"),
        ("s31", "11.99", 31, False, "12"),
        ("s31", "12", 31, True, "12"),
        ("s30", "15.99", 30, False, "16"),
        ("s30", "16", 30, True, "16"),
        ("s11", "15", 11, False, "16"),
        ("s11", "16", 11, True, "16"),
        ("s10", "20", 10, False, "20"),
        ("debt", "18", 0, False, "18"),
    ],
)
def test_interest_rate_slabs(api, kind, rate, expected_score, approved, corrected):
    customer = _customer(kind)
    assert calculate_credit_score(customer) == expected_score

    response = api.post(
        "/check-eligibility",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "100000",
            "interest_rate": rate,
            "tenure": 12,
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval"] is approved
    assert Decimal(str(body["interest_rate"])) == Decimal(rate)
    assert Decimal(str(body["corrected_interest_rate"])) == Decimal(corrected)
    assert body["customer_id"] == customer.customer_id
    assert customer.loans.count() == _existing_loans(kind)
    if approved:
        assert "message" not in body
    elif kind in {"s10", "debt"}:
        assert body["message"] == f"Loan not approved (credit score {expected_score})"
    else:
        assert "interest rate must be at least" in body["message"]


def _existing_loans(kind):
    return {"new": 0, "s51": 1, "s31": 1, "s30": 1, "s11": 7, "s10": 8, "debt": 1}[kind]


@pytest.mark.django_db
def test_emi_equal_to_half_salary_is_still_eligible(api):
    today = timezone.now().date()
    customer = make_customer(monthly_salary=200000)
    make_loan(
        customer,
        loan_amount=Decimal("0.00"),
        tenure=10,
        emis_paid_on_time=10,
        monthly_installment=Decimal("100000.00"),
        start_date=date(today.year - 1, 6, 1),
        end_date=date(today.year + 1, 1, 1),
    )
    assert calculate_credit_score(customer) > 50

    response = api.post(
        "/check-eligibility",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "10000",
            "interest_rate": "5",
            "tenure": 12,
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["approval"] is True


@pytest.mark.django_db
def test_emi_above_half_salary_rejects_before_scoring(api):
    today = timezone.now().date()
    customer = make_customer(monthly_salary=200000)
    make_loan(
        customer,
        monthly_installment=Decimal("100001.00"),
        start_date=date(today.year - 1, 6, 1),
        end_date=date(today.year + 1, 1, 1),
    )
    before = customer.loans.count()
    response = api.post(
        "/check-eligibility",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "10000",
            "interest_rate": "20",
            "tenure": 12,
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "customer_id": customer.customer_id,
        "approval": False,
        "message": "Sum of current EMIs > 50% of monthly salary",
    }
    assert customer.loans.count() == before


def test_emi_formula_matches_known_values():
    assert calculate_emi(Decimal("120000"), Decimal("12"), 12) == Decimal("10661.85")
    assert calculate_emi(Decimal("100000"), Decimal("14"), 12) == Decimal("8978.71")
    assert calculate_emi(Decimal("120000"), Decimal("0"), 12) == Decimal("10000.00")
