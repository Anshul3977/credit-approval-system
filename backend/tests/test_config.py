import pytest
from django.core.exceptions import ImproperlyConfigured

from credit_system.database_url import DatabaseURLError, database_config_from_url
from credit_system.env import env_bool, resolve_secret_key


def test_database_url_parses_render_credentials_and_ssl():
    config = database_config_from_url(
        "postgres://credit_user:p%40ss@dpg-example.oregon-postgres.render.com:5432/credit_db?sslmode=require"
    )
    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "credit_db"
    assert config["USER"] == "credit_user"
    assert config["PASSWORD"] == "p@ss"
    assert config["HOST"] == "dpg-example.oregon-postgres.render.com"
    assert config["PORT"] == "5432"
    assert config["OPTIONS"] == {"sslmode": "require"}


def test_database_url_accepts_sqlalchemy_style_scheme():
    config = database_config_from_url("postgresql://postgres:postgres@localhost/credit_db")
    assert config["NAME"] == "credit_db"
    assert config["PORT"] == "5432"
    assert config["OPTIONS"] == {}


def test_database_url_rejects_other_schemes():
    with pytest.raises(DatabaseURLError):
        database_config_from_url("mysql://localhost/credit_db")


def test_render_refuses_a_missing_or_placeholder_secret():
    with pytest.raises(ImproperlyConfigured):
        resolve_secret_key("", running_on_render=True)
    with pytest.raises(ImproperlyConfigured):
        resolve_secret_key("dev-only-not-for-production", running_on_render=True)
    assert resolve_secret_key("real-secret", running_on_render=True) == "real-secret"


def test_local_process_can_fall_back_to_the_dev_secret():
    assert resolve_secret_key("", running_on_render=False) == "dev-only-not-for-production"
    assert resolve_secret_key("local-key", running_on_render=False) == "local-key"


def test_env_bool_parses_strings():
    assert env_bool("UNSET_BOOL_FOR_TEST", False) is False
    assert env_bool("UNSET_BOOL_FOR_TEST", True) is True
