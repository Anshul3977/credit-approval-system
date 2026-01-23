from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from .serializers import RegisterSerializer
from .models import Customer
from loans.models import Loan
from loans.utils import calculate_credit_score, calculate_emi

# ──────────────────────────────────────────────
# 1. Register new customer
# ──────────────────────────────────────────────
class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            customer = serializer.save()
            response_data = {
                "customer_id": customer.customer_id,
                "name": f"{customer.first_name} {customer.last_name}",
                "age": customer.age,
                "monthly_income": customer.monthly_salary,
                "approved_limit": customer.approved_limit,
                "phone_number": customer.phone_number
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────────
# 2. Check loan eligibility
# ──────────────────────────────────────────────
class CheckEligibilityView(APIView):
    def post(self, request):
        data = request.data

        required = ['customer_id', 'loan_amount', 'interest_rate', 'tenure']
        missing = [k for k in required if k not in data]
        if missing:
            return Response(
                {"error": f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer_id = int(data['customer_id'])
            loan_amount = Decimal(str(data['loan_amount']))
            interest_rate = Decimal(str(data['interest_rate']))
            tenure = int(data['tenure'])

            if loan_amount <= 0:
                raise ValueError("Loan amount must be positive")
            if interest_rate < 0:
                raise ValueError("Interest rate cannot be negative")
            if tenure <= 0:
                raise ValueError("Tenure must be positive")

        except (ValueError, InvalidOperation) as e:
            return Response(
                {"error": f"Invalid input values: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        active_loans = customer.loans.filter(end_date__gt=timezone.now().date())
        current_emis = sum(loan.monthly_installment for loan in active_loans)
        salary = Decimal(customer.monthly_salary)

        if current_emis > Decimal('0.5') * salary:
            return Response({
                "customer_id": customer.customer_id,
                "approval": False,
                "message": "Sum of current EMIs > 50% of monthly salary"
            }, status=status.HTTP_200_OK)

        credit_score = calculate_credit_score(customer)

        if credit_score > 50:
            approved = True
            min_rate = Decimal('0')
        elif credit_score > 30:
            approved = interest_rate >= Decimal('12')
            min_rate = Decimal('12')
        elif credit_score > 10:
            approved = interest_rate >= Decimal('16')
            min_rate = Decimal('16')
        else:
            approved = False
            min_rate = Decimal('16')

        corrected_rate = max(interest_rate, min_rate) if not approved else interest_rate
        monthly_installment = calculate_emi(loan_amount, corrected_rate, tenure)

        response = {
            "customer_id": customer.customer_id,
            "approval": approved,
            "interest_rate": float(interest_rate),
            "corrected_interest_rate": float(corrected_rate),
            "tenure": tenure,
            "monthly_installment": float(monthly_installment)
        }

        if not approved:
            response["message"] = f"Loan not approved (credit score {credit_score})"

        return Response(response, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# 3. Create loan if eligible
# ──────────────────────────────────────────────
class CreateLoanView(APIView):
    def post(self, request):
        data = request.data
        required = ['customer_id', 'loan_amount', 'interest_rate', 'tenure']
        if not all(k in data for k in required):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(customer_id=data['customer_id'])
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        loan_amount = Decimal(str(data['loan_amount']))
        interest_rate = Decimal(str(data['interest_rate']))
        tenure = int(data['tenure'])

        active_loans = customer.loans.filter(end_date__gt=timezone.now().date())
        current_emis = sum(loan.monthly_installment for loan in active_loans)
        if current_emis > Decimal('0.5') * Decimal(customer.monthly_salary):
            return Response({
                "loan_id": None,
                "customer_id": customer.customer_id,
                "loan_approved": False,
                "message": "Sum of current EMIs > 50% of monthly salary",
                "monthly_installment": 0.0
            }, status=status.HTTP_200_OK)

        credit_score = calculate_credit_score(customer)

        if credit_score > 50:
            approved = True
            min_rate = Decimal('0')
        elif credit_score > 30:
            approved = interest_rate >= Decimal('12')
            min_rate = Decimal('12')
        elif credit_score > 10:
            approved = interest_rate >= Decimal('16')
            min_rate = Decimal('16')
        else:
            approved = False
            min_rate = Decimal('16')

        corrected_rate = max(interest_rate, min_rate) if not approved else interest_rate
        monthly_installment = calculate_emi(loan_amount, corrected_rate, tenure)

        if not approved:
            return Response({
                "loan_id": None,
                "customer_id": customer.customer_id,
                "loan_approved": False,
                "message": f"Loan not approved (credit score {credit_score})",
                "monthly_installment": float(monthly_installment)
            }, status=status.HTTP_200_OK)

        # Create loan
        loan = Loan.objects.create(
            customer=customer,
            loan_amount=loan_amount,
            interest_rate=corrected_rate,
            tenure=tenure,
            monthly_installment=monthly_installment,
            emis_paid_on_time=0,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=tenure*30)
        )

        # Update debt
        customer.current_debt += loan_amount
        customer.save()

        return Response({
            "loan_id": loan.loan_id,
            "customer_id": customer.customer_id,
            "loan_approved": True,
            "message": "Loan approved and created",
            "monthly_installment": float(monthly_installment)
        }, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────
# 4. View single loan
# ──────────────────────────────────────────────
class ViewLoanView(APIView):
    def get(self, request, loan_id):
        try:
            loan = Loan.objects.get(loan_id=loan_id)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=status.HTTP_404_NOT_FOUND)

        customer = loan.customer
        response = {
            "loan_id": loan.loan_id,
            "customer": {
                "id": customer.customer_id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "phone_number": customer.phone_number,
                "age": customer.age
            },
            "loan_amount": float(loan.loan_amount),
            "interest_rate": float(loan.interest_rate),
            "monthly_installment": float(loan.monthly_installment),
            "tenure": loan.tenure
        }
        return Response(response, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# 5. View all loans for customer
# ──────────────────────────────────────────────
class ViewLoansView(APIView):
    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(customer_id=customer_id)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        loans = customer.loans.all()
        response = []
        for loan in loans:
            response.append({
                "loan_id": loan.loan_id,
                "loan_amount": float(loan.loan_amount),
                "interest_rate": float(loan.interest_rate),
                "monthly_installment": float(loan.monthly_installment),
                "repayments_left": loan.tenure - loan.emis_paid_on_time
            })
        return Response(response, status=status.HTTP_200_OK)