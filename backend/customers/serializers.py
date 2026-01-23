from rest_framework import serializers
from .models import Customer
from decimal import Decimal

class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    age = serializers.IntegerField(min_value=18)
    monthly_income = serializers.IntegerField(min_value=0)
    phone_number = serializers.IntegerField()

    def create(self, validated_data):
        monthly_salary = validated_data['monthly_income']
        # approved_limit = 36 * monthly_salary rounded to nearest lakh
        approved_limit = round(monthly_salary * 36 / 100000) * 100000

        customer = Customer.objects.create(
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            age=validated_data['age'],
            monthly_salary=monthly_salary,
            approved_limit=approved_limit,
            phone_number=validated_data['phone_number'],
            current_debt=Decimal('0.00')
        )
        return customer