"""
Django settings for the credit approval API.

Production (including Render) reads configuration from the environment.
DEBUG defaults to off. A development secret is used only when DJANGO_SECRET_KEY
is unset and the process is not running on Render.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .database_url import DatabaseURLError, database_config_from_url
from .env import env_bool, env_csv, load_dotenv, on_render, resolve_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = resolve_secret_key(
    os.environ.get("DJANGO_SECRET_KEY", ""),
    running_on_render=on_render(),
)
DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS") or ["localhost", "127.0.0.1"]
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_host and render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_host)
if "pytest" in sys.modules and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS")
render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
if render_url and render_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(render_url)
elif render_host:
    origin = f"https://{render_host}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "customers",
    "loans",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "credit_system.urls"
APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "credit_system.wsgi.application"

database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url:
    try:
        default_database = database_config_from_url(database_url)
    except DatabaseURLError as exc:
        raise ImproperlyConfigured(str(exc)) from exc
else:
    default_database = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "credit_db"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "OPTIONS": {},
    }

# Persistent connections keep a free-tier web process from reconnecting per
# request. Tests need a fresh connection so pytest-django can wrap transactions.
if "pytest" in sys.modules:
    default_database["CONN_MAX_AGE"] = 0
else:
    default_database["CONN_MAX_AGE"] = int(os.environ.get("DB_CONN_MAX_AGE", "60"))

DATABASES = {"default": default_database}

_broker = os.environ.get("CELERY_BROKER_URL", "").strip() or "memory://"
CELERY_BROKER_URL = _broker
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "").strip() or None
# Eager when asked, and also when nobody configured a real broker.
CELERY_TASK_ALWAYS_EAGER = env_bool(
    "CELERY_TASK_ALWAYS_EAGER",
    default=_broker.startswith("memory"),
)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Render terminates TLS at the proxy. Health checks arrive as plain HTTP, so
# do not redirect to HTTPS inside the app.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Credit Approval API",
    "DESCRIPTION": (
        "Register customers, check loan eligibility from repayment history, "
        "and create or view loans. The approval slabs are documented on "
        "POST /check-eligibility. This service does not authenticate callers."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
