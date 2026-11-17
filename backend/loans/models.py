
from django.db import models
from django.utils import timezone

from customers.models import Customer


class Loan(models.Model):
    loan_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loans')
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=4)  # e.g. 14.5000
    tenure = models.PositiveIntegerField()  # months
    monthly_installment = models.DecimalField(max_digits=15, decimal_places=2)  # EMI
    emis_paid_on_time = models.PositiveIntegerField(default=0)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()

    def __str__(self):
        return f"Loan {self.loan_id} for {self.customer}"

    def repayments_left(self):
        return max(0, self.tenure - self.emis_paid_on_time)

    class Meta:
        ordering = ['-start_date']