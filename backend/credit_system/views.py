import logging

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    database = serializers.CharField()


class ServiceIndexSerializer(serializers.Serializer):
    service = serializers.CharField()
    health = serializers.CharField()
    docs = serializers.CharField()
    schema = serializers.CharField()
    endpoints = serializers.ListField(child=serializers.CharField())


class ServiceIndexView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Service index", responses={200: ServiceIndexSerializer})
    def get(self, request):
        return Response(
            {
                "service": "Credit Approval API",
                "health": "/health",
                "docs": "/api/docs/",
                "schema": "/api/schema/",
                "endpoints": [
                    "POST /register",
                    "POST /check-eligibility",
                    "POST /create-loan",
                    "GET /view-loan/<loan_id>",
                    "GET /view-loans/<customer_id>",
                ],
            }
        )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Health check",
        responses={200: HealthSerializer, 503: HealthSerializer},
    )
    def get(self, request):
        database = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            # The exception text can include the database URL. Log the type only.
            logger.warning("Database health check failed")
            database = "unavailable"
        status_code = 200 if database == "ok" else 503
        return Response(
            {"status": "ok" if database == "ok" else "degraded", "database": database},
            status=status_code,
        )
