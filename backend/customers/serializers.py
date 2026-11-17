from decimal import Decimal

from rest_framework import serializers

from .models import Customer


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    age = serializers.IntegerField(min_value=18)
    monthly_income = serializers.IntegerField(min_value=0)
    phone_number = serializers.IntegerField(min_value=0)

    def validate_phone_number(self, value):
        if Customer.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def create(self, validated_data):
        monthly_salary = validated_data["monthly_income"]
        # 36 * monthly salary, rounded to the nearest lakh (100000).
        # Python round() uses half-to-even when the value lands on .5.
        approved_limit = round(monthly_salary * 36 / 100000) * 100000
        return Customer.objects.create(
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            age=validated_data["age"],
            monthly_salary=monthly_salary,
            approved_limit=approved_limit,
            phone_number=validated_data["phone_number"],
            current_debt=Decimal("0.00"),
        )


class RegisterResponseSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    name = serializers.CharField()
    age = serializers.IntegerField()
    monthly_income = serializers.IntegerField()
    approved_limit = serializers.IntegerField()
    phone_number = serializers.IntegerField()


class LoanRequestSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    loan_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = serializers.DecimalField(max_digits=6, decimal_places=4)
    tenure = serializers.IntegerField()


class ErrorSerializer(serializers.Serializer):
    error = serializers.CharField()


class EligibilityResponseSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    approval = serializers.BooleanField()
    interest_rate = serializers.FloatField(required=False)
    corrected_interest_rate = serializers.FloatField(required=False)
    tenure = serializers.IntegerField(required=False)
    monthly_installment = serializers.FloatField(required=False)
    message = serializers.CharField(required=False)


class CreateLoanResponseSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField(allow_null=True)
    customer_id = serializers.IntegerField()
    loan_approved = serializers.BooleanField()
    message = serializers.CharField()
    monthly_installment = serializers.FloatField()


class LoanCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.IntegerField()
    age = serializers.IntegerField(allow_null=True)


class ViewLoanResponseSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField()
    customer = LoanCustomerSerializer()
    loan_amount = serializers.FloatField()
    interest_rate = serializers.FloatField()
    monthly_installment = serializers.FloatField()
    tenure = serializers.IntegerField()


class ViewLoansItemSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField()
    loan_amount = serializers.FloatField()
    interest_rate = serializers.FloatField()
    monthly_installment = serializers.FloatField()
    repayments_left = serializers.IntegerField()
