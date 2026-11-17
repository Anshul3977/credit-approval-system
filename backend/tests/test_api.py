from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from loans.models import Loan

from .factories import make_customer, make_loan


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_register_rounds_approved_limit_to_the_nearest_lakh(api):
    response = api.post(
        "/register",
        {
            "first_name": "Asha",
            "last_name": "Rao",
            "age": 28,
            "monthly_income": 50000,
            "phone_number": 9811111111,
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Asha Rao"
    assert body["monthly_income"] == 50000
    assert body["approved_limit"] == 1_800_000
    assert body["phone_number"] == 9811111111

    low = api.post(
        "/register",
        {
            "first_name": "Dev",
            "last_name": "Shah",
            "age": 22,
            "monthly_income": 10000,
            "phone_number": 9811111112,
        },
        format="json",
    )
    assert low.status_code == 201
    assert low.json()["approved_limit"] == 400_000

    mid = api.post(
        "/register",
        {
            "first_name": "Mina",
            "last_name": "Iyer",
            "age": 31,
            "monthly_income": 33000,
            "phone_number": 9811111113,
        },
        format="json",
    )
    assert mid.status_code == 201
    assert mid.json()["approved_limit"] == 1_200_000


@pytest.mark.django_db
def test_register_rejects_invalid_and_duplicate_customers(api):
    missing = api.post("/register", {"first_name": "Only"}, format="json")
    assert missing.status_code == 400

    young = api.post(
        "/register",
        {
            "first_name": "Isha",
            "last_name": "Nair",
            "age": 17,
            "monthly_income": 40000,
            "phone_number": 9811111114,
        },
        format="json",
    )
    assert young.status_code == 400
    assert "age" in young.json()

    first = api.post(
        "/register",
        {
            "first_name": "Ravi",
            "last_name": "Menon",
            "age": 40,
            "monthly_income": 80000,
            "phone_number": 9811111115,
        },
        format="json",
    )
    assert first.status_code == 201
    duplicate = api.post(
        "/register",
        {
            "first_name": "Ravi",
            "last_name": "Menon",
            "age": 40,
            "monthly_income": 80000,
            "phone_number": 9811111115,
        },
        format="json",
    )
    assert duplicate.status_code == 400
    assert "already registered" in duplicate.json()["phone_number"][0]


@pytest.mark.django_db
def test_check_eligibility_rejects_bad_input_and_unknown_customers(api):
    customer = make_customer()
    missing = api.post(
        "/check-eligibility",
        {"customer_id": customer.customer_id, "loan_amount": "1000"},
        format="json",
    )
    assert missing.status_code == 400
    assert "tenure" in missing.json()["error"]

    invalid = api.post(
        "/check-eligibility",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "-5",
            "interest_rate": "10",
            "tenure": 12,
        },
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"].startswith("Invalid input values:")

    huge = api.post(
        "/check-eligibility",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "1000",
            "interest_rate": "12",
            "tenure": 5000,
        },
        format="json",
    )
    assert huge.status_code == 400

    missing_customer = api.post(
        "/check-eligibility",
        {
            "customer_id": 999999,
            "loan_amount": "1000",
            "interest_rate": "12",
            "tenure": 12,
        },
        format="json",
    )
    assert missing_customer.status_code == 404
    assert missing_customer.json() == {"error": "Customer not found"}


@pytest.mark.django_db
def test_create_loan_persists_debt_and_can_be_viewed(api):
    created = api.post(
        "/register",
        {
            "first_name": "Asha",
            "last_name": "Rao",
            "age": 28,
            "monthly_income": 50000,
            "phone_number": 9811111120,
        },
        format="json",
    )
    customer_id = created.json()["customer_id"]

    rejected = api.post(
        "/create-loan",
        {
            "customer_id": customer_id,
            "loan_amount": "100000",
            "interest_rate": "10",
            "tenure": 12,
        },
        format="json",
    )
    assert rejected.status_code == 200
    assert rejected.json()["loan_approved"] is False
    assert rejected.json()["loan_id"] is None
    assert "at least 12" in rejected.json()["message"]
    assert Loan.objects.filter(customer_id=customer_id).count() == 0

    approved = api.post(
        "/create-loan",
        {
            "customer_id": customer_id,
            "loan_amount": "100000",
            "interest_rate": "14",
            "tenure": 12,
        },
        format="json",
    )
    assert approved.status_code == 201
    body = approved.json()
    assert body["loan_approved"] is True
    assert body["message"] == "Loan approved and created"
    assert Decimal(str(body["monthly_installment"])) == Decimal("8978.71")

    loan = Loan.objects.get(loan_id=body["loan_id"])
    assert loan.interest_rate == Decimal("14.0000")
    assert loan.customer.current_debt == Decimal("100000.00")
    assert loan.end_date == loan.start_date + timedelta(days=360)

    detail = api.get(f"/view-loan/{loan.loan_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["customer"]["first_name"] == "Asha"
    assert detail_body["customer"]["id"] == customer_id
    assert detail_body["tenure"] == 12
    assert Decimal(str(detail_body["loan_amount"])) == Decimal("100000")

    listing = api.get(f"/view-loans/{customer_id}")
    assert listing.status_code == 200
    assert listing.json() == [
        {
            "loan_id": loan.loan_id,
            "loan_amount": 100000.0,
            "interest_rate": 14.0,
            "monthly_installment": 8978.71,
            "repayments_left": 12,
        }
    ]


@pytest.mark.django_db
def test_create_loan_emi_burden_does_not_insert(api):
    today = timezone.now().date()
    customer = make_customer(monthly_salary=100000)
    make_loan(
        customer,
        monthly_installment=Decimal("60000.00"),
        start_date=today,
        end_date=today.replace(year=today.year + 1),
    )
    response = api.post(
        "/create-loan",
        {
            "customer_id": customer.customer_id,
            "loan_amount": "10000",
            "interest_rate": "18",
            "tenure": 6,
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["loan_approved"] is False
    assert response.json()["monthly_installment"] == 0.0
    assert response.json()["message"] == "Sum of current EMIs > 50% of monthly salary"
    assert customer.loans.count() == 1
    customer.refresh_from_db()
    assert customer.current_debt == Decimal("0.00")


@pytest.mark.django_db
def test_view_endpoints_cover_missing_rows_and_clamped_repayments(api):
    assert api.get("/view-loan/404").status_code == 404
    assert api.get("/view-loan/404").json() == {"error": "Loan not found"}
    assert api.get("/view-loans/404").status_code == 404

    customer = make_customer()
    assert api.get(f"/view-loans/{customer.customer_id}").json() == []

    loan = make_loan(customer, tenure=5, emis_paid_on_time=9, loan_amount=Decimal("2500.50"))
    listing = api.get(f"/view-loans/{customer.customer_id}")
    assert listing.json()[0]["repayments_left"] == 0
    assert listing.json()[0]["loan_id"] == loan.loan_id

    malformed = api.post("/create-loan", {"customer_id": "nope"}, format="json")
    assert malformed.status_code == 400
    unknown = api.post(
        "/create-loan",
        {
            "customer_id": 999999,
            "loan_amount": "1000",
            "interest_rate": "12",
            "tenure": 6,
        },
        format="json",
    )
    assert unknown.status_code == 404


@pytest.mark.django_db
def test_health_docs_and_index(api):
    health = api.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}

    index = api.get("/")
    assert index.status_code == 200
    assert index.json()["docs"] == "/api/docs/"
    assert "POST /check-eligibility" in index.json()["endpoints"]

    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "/check-eligibility" in schema.content.decode()

    docs = api.get("/api/docs/")
    assert docs.status_code == 200
    assert "swagger" in docs.content.decode().lower()
