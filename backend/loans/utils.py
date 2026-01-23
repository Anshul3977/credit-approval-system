from django.utils import timezone
from decimal import Decimal
from .models import Loan

def calculate_credit_score(customer):
    loans = customer.loans.all()
    if not loans.exists():
        return 50  # neutral for new customers

    total_loans = loans.count()

    # i. Past Loans paid on time (%)
    on_time_pct = sum(
        (loan.emis_paid_on_time / loan.tenure) if loan.tenure > 0 else 1
        for loan in loans
    ) / total_loans * 100

    # ii. No of loans taken in past (fewer better)
    num_loans_score = max(0, 40 - (total_loans * 5))

    # iii. Loan activity in current year
    current_year = timezone.now().year
    loans_this_year = loans.filter(start_date__year=current_year).count()
    activity_score = max(0, 30 - (loans_this_year * 10))

    # iv. Loan approved volume
    total_approved = sum(loan.loan_amount for loan in loans)
    volume_score = min(50, 50 - (total_approved / customer.approved_limit * 50 if customer.approved_limit > 0 else 0))

    # v. Hard rule: current debt > approved limit → 0
    current_debt = customer.current_debt  # already updated in ingestion
    if current_debt > customer.approved_limit:
        return 0

    # Combine (adjust weights if needed)
    score = (
        on_time_pct * 0.4 +
        num_loans_score * 0.2 +
        activity_score * 0.2 +
        volume_score * 0.2
    )
    return max(0, min(100, int(score)))


def calculate_emi(principal: Decimal, annual_rate: Decimal, tenure: int) -> Decimal:
    if annual_rate == 0:
        return principal / Decimal(tenure)
    r = annual_rate / Decimal('1200')
    n = tenure
    emi = principal * r * (Decimal(1) + r)**n / ((Decimal(1) + r)**n - Decimal(1))
    return emi.quantize(Decimal('0.01'))