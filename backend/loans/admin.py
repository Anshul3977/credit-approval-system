from django.contrib import admin

from .models import Loan


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "loan_id",
        "customer",
        "loan_amount",
        "interest_rate",
        "tenure",
        "monthly_installment",
        "emis_paid_on_time",
        "start_date",
        "end_date",
    )
    list_select_related = ("customer",)
    search_fields = ("customer__first_name", "customer__last_name", "loan_id")
