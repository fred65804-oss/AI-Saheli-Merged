"""Regression tests for upgrades of auth databases created by older releases."""

from sqlalchemy import create_engine, inspect, text

from apps.backend.auth.db import _migrate_schema


def test_migrate_schema_adds_role_to_existing_users_table():
    legacy_engine = create_engine("sqlite:///:memory:")

    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id VARCHAR(36) PRIMARY KEY NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users (
                    id, email, name, hashed_password, is_active, created_at
                ) VALUES (
                    'user-1', 'legacy@example.com', 'Legacy User',
                    'hash', 1, '2026-01-01 00:00:00'
                )
                """
            )
        )

    _migrate_schema(legacy_engine)
    _migrate_schema(legacy_engine)

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("users")}
    assert "role" in columns

    with legacy_engine.connect() as connection:
        role = connection.execute(
            text("SELECT role FROM users WHERE id = 'user-1'")
        ).scalar_one()
    assert role == "citizen"
