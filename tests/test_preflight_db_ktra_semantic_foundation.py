import inspect

import pytest

from tools import preflight_db_ktra_semantic_foundation as preflight


def test_preflight_refuses_non_rehearsal_or_non_postgres_targets():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        preflight.require_rehearsal_postgres("sqlite:///artifact.db")
    with pytest.raises(RuntimeError, match="expected"):
        preflight.require_rehearsal_postgres("postgresql+psycopg://user:password@host/another_db")


def test_preflight_is_explicit_read_only_and_never_contains_write_sql():
    source = inspect.getsource(preflight.run_preflight)

    assert "SET TRANSACTION READ ONLY" in source
    assert "SHOW transaction_read_only" in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source
    assert preflight.REQUIRED_DATABASE_NAME == "gxp_legacy_rehearsal"


def test_preflight_normalizes_display_labels_only_for_compatibility_evidence():
    assert preflight.normalize_role_label("  Trưởng   đoàn  ") == "truong doan"
