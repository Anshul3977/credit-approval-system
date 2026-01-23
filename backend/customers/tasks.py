import pandas as pd
from celery import shared_task
from .models import Customer
from loans.models import Loan
from datetime import datetime
from pathlib import Path
from django.utils import timezone
from django.db import models
from decimal import Decimal

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / 'data'

@shared_task
def ingest_initial_data():
    print("Starting data ingestion...")

    # Customers
    cust_path = DATA_DIR / 'customer_data.xlsx'
    if cust_path.exists():
        df = pd.read_excel(cust_path)
        for _, row in df.iterrows():
            Customer.objects.update_or_create(
                customer_id=row['Customer ID'],
                defaults={
                    'first_name': row['First Name'],
                    'last_name': row['Last Name'],
                    'age': row.get('Age'),
                    'phone_number': row['Phone Number'],
                    'monthly_salary': row['Monthly Salary'],
                    'approved_limit': row['Approved Limit'],
                    'current_debt': 0.00,  # will update later from loans
                }
            )
        print(f"Ingested {len(df)} customers")
    else:
        print("customer_data.xlsx not found!")

    # Loans
    loan_path = DATA_DIR / 'loan_data.xlsx'
    if loan_path.exists():
        df = pd.read_excel(loan_path)
        print("Loan Data columns:", list(df.columns))  # Debug: confirm columns

        for idx, row in df.iterrows():
            try:
                customer_id = int(row['Customer ID'])
                customer = Customer.objects.get(customer_id=customer_id)

                Loan.objects.update_or_create(
                    loan_id=idx + 1,  # temporary auto-generated loan_id
                    defaults={
                        'customer': customer,
                        'loan_amount': row['Loan Amount'],
                        'interest_rate': row['Interest Rate'],
                        'tenure': row['Tenure'],
                        'monthly_installment': row['Monthly payment'],
                        'emis_paid_on_time': row['EMIs paid on Time'],
                        'start_date': row['Date of Approval'],
                        'end_date': row['End Date'],
                    }
                )
            except KeyError as e:
                print(f"Column missing in row {idx}: {e}")
            except Customer.DoesNotExist:
                print(f"Customer {customer_id} not found for loan row {idx}")
            except Exception as e:
                print(f"Error in loan row {idx}: {e}")
        print(f"Processed {len(df)} loan rows")
    else:
        print("loan_data.xlsx not found!")

    # Update current_debt for each customer (active loans only)
    for customer in Customer.objects.all():
        active_loans_sum = customer.loans.filter(
            end_date__gt=timezone.now().date()
        ).aggregate(total=models.Sum('loan_amount'))['total'] or Decimal('0.00')
        customer.current_debt = active_loans_sum
        customer.save()

    print("Data ingestion completed!")