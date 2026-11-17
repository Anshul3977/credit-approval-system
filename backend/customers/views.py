from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from loans.models import Loan
from loans.utils import evaluate_eligibility, loan_end_date

from .models import Customer
from .serializers import (
    CreateLoanResponseSerializer,
    EligibilityResponseSerializer,
    ErrorSerializer,
    LoanRequestSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    ViewLoanResponseSerializer,
    ViewLoansItemSerializer,
)

_MAX_TENURE_MONTHS = 1200

_ELIGIBILITY_DESCRIPTION = """
Credit score is an integer from 0 to 100 (`loans.utils.calculate_credit_score`).

- A customer with no loans scores 50.
- If the customer has at least one loan and current_debt is above
  approved_limit, the score is 0.
- Otherwise the score mixes on-time EMI share, how many loans they have,
  how many started this year, and historical loan volume against the limit.

Approval uses that score and the requested annual interest rate:

- score > 50: approve at the requested rate
- 30 < score <= 50: approve only if the rate is at least 12. Below that,
  reject and set corrected_interest_rate to 12
- 10 < score <= 30: approve only if the rate is at least 16. Below that,
  reject and set corrected_interest_rate to 16
- score <= 10: reject, and leave corrected_interest_rate equal to the
  requested rate

If the sum of monthly installments on loans that have not ended yet is
greater than half of monthly salary, the loan is rejected before scoring.
A sum equal to half of salary is still eligible.
""".strip()


def _error(message, http_status):
    return Response({"error": message}, status=http_status)


def _parse_loan_request(data):
    required = ["customer_id", "loan_amount", "interest_rate", "tenure"]
    missing = [key for key in required if key not in data or data.get(key) in ("", None)]
    if missing:
        return None, _error(
            f"Missing required fields: {', '.join(missing)}",
            status.HTTP_400_BAD_REQUEST,
        )
    try:
        customer_id = _parse_int(data["customer_id"], "customer_id")
        loan_amount = _parse_decimal(data["loan_amount"], "loan_amount")
        interest_rate = _parse_decimal(data["interest_rate"], "interest_rate")
        tenure = _parse_int(data["tenure"], "tenure")
        if customer_id <= 0:
            raise ValueError("customer_id must be positive")
        if loan_amount <= 0:
            raise ValueError("Loan amount must be positive")
        if interest_rate < 0:
            raise ValueError("Interest rate cannot be negative")
        if tenure <= 0 or tenure > _MAX_TENURE_MONTHS:
            raise ValueError(f"Tenure must be between 1 and {_MAX_TENURE_MONTHS} months")
    except (ValueError, InvalidOperation, TypeError) as exc:
        return None, _error(f"Invalid input values: {exc}", status.HTTP_400_BAD_REQUEST)
    return (customer_id, loan_amount, interest_rate, tenure), None


def _parse_int(value, label):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, str) and not value.strip().lstrip("-").isdigit():
        raise ValueError(f"{label} must be an integer")
    return int(value)


def _parse_decimal(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not number.is_finite():
        raise ValueError(f"{label} must be a finite number")
    return number


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["customers"],
        summary="Register a customer",
        description=(
            "approved_limit is 36 times monthly_income, rounded to the nearest "
            "lakh (100000) with Python's round()."
        ),
        request=RegisterSerializer,
        responses={201: RegisterResponseSerializer},
        examples=[
            OpenApiExample(
                "Monthly income 50000",
                value={
                    "first_name": "Asha",
                    "last_name": "Rao",
                    "age": 28,
                    "monthly_income": 50000,
                    "phone_number": 9811111111,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = serializer.save()
        except IntegrityError:
            return Response(
                {"phone_number": ["Phone number already registered."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "customer_id": customer.customer_id,
                "name": f"{customer.first_name} {customer.last_name}",
                "age": customer.age,
                "monthly_income": customer.monthly_salary,
                "approved_limit": customer.approved_limit,
                "phone_number": customer.phone_number,
            },
            status=status.HTTP_201_CREATED,
        )


class CheckEligibilityView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["loans"],
        summary="Check loan eligibility",
        description=_ELIGIBILITY_DESCRIPTION,
        request=LoanRequestSerializer,
        responses={
            200: EligibilityResponseSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request):
        parsed, error = _parse_loan_request(request.data)
        if error is not None:
            return error
        customer_id, loan_amount, interest_rate, tenure = parsed
        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return _error("Customer not found", status.HTTP_404_NOT_FOUND)

        decision = evaluate_eligibility(customer, loan_amount, interest_rate, tenure)
        if decision.reason == "emi":
            return Response(
                {
                    "customer_id": customer.customer_id,
                    "approval": False,
                    "message": decision.message,
                },
                status=status.HTTP_200_OK,
            )
        body = {
            "customer_id": customer.customer_id,
            "approval": decision.approved,
            "interest_rate": float(decision.interest_rate),
            "corrected_interest_rate": float(decision.corrected_interest_rate),
            "tenure": tenure,
            "monthly_installment": float(decision.monthly_installment),
        }
        if decision.message:
            body["message"] = decision.message
        return Response(body, status=status.HTTP_200_OK)


class CreateLoanView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["loans"],
        summary="Create a loan when the customer is eligible",
        description=(
            "Uses the same rules as /check-eligibility. A rejection is HTTP 200 "
            "with loan_approved false. An approval is HTTP 201 and adds the "
            "loan amount to current_debt. The stored end date is the start date "
            "plus tenure times 30 days."
        ),
        request=LoanRequestSerializer,
        responses={
            201: CreateLoanResponseSerializer,
            200: CreateLoanResponseSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request):
        parsed, error = _parse_loan_request(request.data)
        if error is not None:
            return error
        customer_id, loan_amount, interest_rate, tenure = parsed
        if not Customer.objects.filter(customer_id=customer_id).exists():
            return _error("Customer not found", status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(customer_id=customer_id)
            decision = evaluate_eligibility(customer, loan_amount, interest_rate, tenure)
            if not decision.approved:
                return Response(
                    {
                        "loan_id": None,
                        "customer_id": customer.customer_id,
                        "loan_approved": False,
                        "message": decision.message,
                        "monthly_installment": float(decision.monthly_installment),
                    },
                    status=status.HTTP_200_OK,
                )
            today = timezone.now().date()
            loan = Loan.objects.create(
                customer=customer,
                loan_amount=loan_amount,
                interest_rate=decision.corrected_interest_rate,
                tenure=tenure,
                monthly_installment=decision.monthly_installment,
                emis_paid_on_time=0,
                start_date=today,
                end_date=loan_end_date(today, tenure),
            )
            customer.current_debt += loan_amount
            customer.save(update_fields=["current_debt"])

        return Response(
            {
                "loan_id": loan.loan_id,
                "customer_id": customer.customer_id,
                "loan_approved": True,
                "message": "Loan approved and created",
                "monthly_installment": float(decision.monthly_installment),
            },
            status=status.HTTP_201_CREATED,
        )


class ViewLoanView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["loans"],
        summary="View one loan",
        responses={200: ViewLoanResponseSerializer, 404: ErrorSerializer},
    )
    def get(self, request, loan_id):
        try:
            loan = Loan.objects.select_related("customer").get(loan_id=loan_id)
        except Loan.DoesNotExist:
            return _error("Loan not found", status.HTTP_404_NOT_FOUND)
        customer = loan.customer
        return Response(
            {
                "loan_id": loan.loan_id,
                "customer": {
                    "id": customer.customer_id,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "phone_number": customer.phone_number,
                    "age": customer.age,
                },
                "loan_amount": float(loan.loan_amount),
                "interest_rate": float(loan.interest_rate),
                "monthly_installment": float(loan.monthly_installment),
                "tenure": loan.tenure,
            }
        )


class ViewLoansView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["loans"],
        summary="View every loan for a customer",
        responses={200: ViewLoansItemSerializer(many=True), 404: ErrorSerializer},
    )
    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return _error("Customer not found", status.HTTP_404_NOT_FOUND)
        payload = [
            {
                "loan_id": loan.loan_id,
                "loan_amount": float(loan.loan_amount),
                "interest_rate": float(loan.interest_rate),
                "monthly_installment": float(loan.monthly_installment),
                "repayments_left": loan.repayments_left(),
            }
            for loan in customer.loans.all()
        ]
        return Response(payload)
