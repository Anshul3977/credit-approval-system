# Credit Approval System

A complete backend system for credit approval using **Django**, **Django REST Framework**, **PostgreSQL**, **Celery + Redis**, fully dockerized.

Built as part of a backend assignment — includes data ingestion from Excel, customer registration, loan eligibility check, loan creation, and loan viewing APIs.

## Features
- Background ingestion of customer & loan data from Excel files (via Celery task)
- Register new customer → auto-calculate approved limit (36 × monthly salary, rounded to nearest lakh)
- Check loan eligibility → credit score based on history, EMI ≤ 50% salary check, interest rate slabs
- Create loan if eligible → saves Loan record & updates customer's current debt
- View single loan details (loan + customer info)
- View all loans for a customer (with repayments left)

## Tech Stack
- Django 4.2 + Django REST Framework
- PostgreSQL (database)
- Celery + Redis (background tasks)
- Docker + docker-compose (containerization)
- Python 3.11

## How to Run

1. Clone the repository
   ```bash
   git clone https://github.com/Anshul3977/credit-approval-system.git
   cd credit-approval-system
