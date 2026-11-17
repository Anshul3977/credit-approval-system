from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from credit_system.views import HealthView, ServiceIndexView
from customers.views import (
    CheckEligibilityView,
    CreateLoanView,
    RegisterView,
    ViewLoansView,
    ViewLoanView,
)

urlpatterns = [
    path("", ServiceIndexView.as_view(), name="index"),
    path("health", HealthView.as_view(), name="health"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("register", RegisterView.as_view(), name="register"),
    path("check-eligibility", CheckEligibilityView.as_view(), name="check-eligibility"),
    path("create-loan", CreateLoanView.as_view(), name="create-loan"),
    path("view-loan/<int:loan_id>", ViewLoanView.as_view(), name="view-loan"),
    path("view-loans/<int:customer_id>", ViewLoansView.as_view(), name="view-loans"),
]
