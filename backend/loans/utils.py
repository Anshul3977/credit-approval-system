"""Credit score, EMI, and the approval decision shared by the loan endpoints."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

from django.utils import timezone

# Component weights from the original scoring function. Each component is
# bounded to 0..100 (on-time), 0..40 (loan count), 0..30 (this-year activity),
# or 0..50 (approved volume) before weighting.
ON_TIME_WEIGHT = Decimal("0.4")
COUNT_WEIGHT = Decimal("0.2")
ACTIVITY_WEIGHT = Decimal("0.2")
VOLUME_WEIGHT = Decimal("0.2")


@dataclass(frozen=True)
class LoanDecision:
    approved: bool
    credit_score: int | None
    interest_rate: Decimal
    corrected_interest_rate: Decimal
    monthly_installment: Decimal
    message: str | None
    reason: str


def calculate_credit_score(customer) -> int:
    """
    Integer score from 0 to 100.

    A customer with no loans scores 50. That neutral score is not in the
    unrestricted slab (score > 50), so a new customer needs an interest rate
    of at least 12%.

    When the customer has at least one loan and current_debt is above
    approved_limit, the score is 0. Component math uses Decimal so a customer
    with loan history does not crash on float/Decimal mixing. The final score
    is truncated toward zero, then clamped to 0..100.
    """
    loans = list(customer.loans.all())
    if not loans:
        return 50

    if customer.current_debt > customer.approved_limit:
        return 0

    ratios = []
    for loan in loans:
        if loan.tenure <= 0:
            ratios.append(Decimal("1"))
            continue
        ratio = Decimal(loan.emis_paid_on_time) / Decimal(loan.tenure)
        ratios.append(min(Decimal("1"), ratio))
    on_time_pct = sum(ratios, Decimal("0")) / Decimal(len(loans)) * Decimal("100")

    num_loans_score = max(0, 40 - (len(loans) * 5))

    current_year = timezone.now().year
    loans_this_year = sum(1 for loan in loans if loan.start_date.year == current_year)
    activity_score = max(0, 30 - (loans_this_year * 10))

    total_approved = sum((loan.loan_amount for loan in loans), Decimal("0"))
    if customer.approved_limit > 0:
        volume_score = Decimal("50") - (
            total_approved / Decimal(customer.approved_limit) * Decimal("50")
        )
        volume_score = min(Decimal("50"), max(Decimal("0"), volume_score))
    else:
        volume_score = Decimal("0")

    score = (
        on_time_pct * ON_TIME_WEIGHT
        + Decimal(num_loans_score) * COUNT_WEIGHT
        + Decimal(activity_score) * ACTIVITY_WEIGHT
        + volume_score * VOLUME_WEIGHT
    )
    truncated = int(score.to_integral_value(rounding=ROUND_DOWN))
    return max(0, min(100, truncated))


def approval_for_score(credit_score: int, interest_rate: Decimal) -> tuple[bool, Decimal]:
    """
    Map a score and a requested annual rate to (approved, rate_to_use).

    Slabs use the original boundaries:
    - score > 50: approve at the requested rate
    - 30 < score <= 50: approve only when the rate is at least 12
    - 10 < score <= 30: approve only when the rate is at least 16
    - score <= 10: reject, and do not rewrite the rate

    A rate below the slab minimum is rejected. corrected_interest_rate is the
    minimum the caller would need to resubmit. Raising the rate does not
    approve a score of 10 or below, so that case keeps the requested rate.
    """
    rate = Decimal(interest_rate)
    if credit_score > 50:
        return True, rate
    if credit_score > 30:
        minimum = Decimal("12")
    elif credit_score > 10:
        minimum = Decimal("16")
    else:
        return False, rate
    if rate >= minimum:
        return True, rate
    return False, minimum


def calculate_emi(principal: Decimal, annual_rate: Decimal, tenure: int) -> Decimal:
    """Standard reducing-balance EMI. A zero rate is principal divided by tenure."""
    principal = Decimal(principal)
    annual_rate = Decimal(annual_rate)
    if annual_rate == 0:
        return (principal / Decimal(tenure)).quantize(Decimal("0.01"))
    monthly_rate = annual_rate / Decimal("1200")
    growth = (Decimal(1) + monthly_rate) ** tenure
    emi = principal * monthly_rate * growth / (growth - Decimal(1))
    return emi.quantize(Decimal("0.01"))


def evaluate_eligibility(customer, loan_amount, interest_rate, tenure) -> LoanDecision:
    """Decide a loan using current EMIs first, then the credit-score slabs."""
    interest_rate = Decimal(interest_rate)
    loan_amount = Decimal(loan_amount)
    today = timezone.now().date()
    active_loans = customer.loans.filter(end_date__gt=today)
    current_emis = sum(
        (loan.monthly_installment for loan in active_loans),
        Decimal("0"),
    )
    salary = Decimal(customer.monthly_salary)
    if current_emis > (Decimal("0.5") * salary):
        return LoanDecision(
            approved=False,
            credit_score=None,
            interest_rate=interest_rate,
            corrected_interest_rate=interest_rate,
            monthly_installment=Decimal("0.00"),
            message="Sum of current EMIs > 50% of monthly salary",
            reason="emi",
        )

    score = calculate_credit_score(customer)
    approved, corrected = approval_for_score(score, interest_rate)
    installment = calculate_emi(loan_amount, corrected, tenure)
    if approved:
        message = None
        reason = "approved"
    elif corrected != interest_rate:
        message = (
            f"Loan not approved (credit score {score}); "
            f"interest rate must be at least {corrected}"
        )
        reason = "interest_rate"
    else:
        message = f"Loan not approved (credit score {score})"
        reason = "credit_score"
    return LoanDecision(
        approved=approved,
        credit_score=score,
        interest_rate=interest_rate,
        corrected_interest_rate=corrected,
        monthly_installment=installment,
        message=message,
        reason=reason,
    )


def loan_end_date(start: date, tenure_months: int) -> date:
    """The original create-loan approximation: tenure months of 30 days each."""
    from datetime import timedelta

    return start + timedelta(days=tenure_months * 30)
