import itertools
from datetime import date
from decimal import Decimal

from customers.models import Customer
from loans.models import Loan

_phones = itertools.count(8100000001)


def make_customer(**overrides):
    defaults = {
        "first_name": "Test",
        "last_name": "User",
        "age": 30,
        "monthly_salary": 200000,
        "approved_limit": 5000000,
        "phone_number": next(_phones),
        "current_debt": Decimal("0.00"),
    }
    defaults.update(overrides)
    return Customer.objects.create(**defaults)


def make_loan(customer, **overrides):
    defaults = {
        "loan_amount": Decimal("0.00"),
        "interest_rate": Decimal("10.00"),
        "tenure": 10,
        "monthly_installment": Decimal("0.00"),
        "emis_paid_on_time": 0,
        "start_date": date(2020, 1, 1),
        "end_date": date(2020, 2, 1),
    }
    defaults.update(overrides)
    return Loan.objects.create(customer=customer, **defaults)
