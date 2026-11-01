import pytest
from backend.tests.conftest import check_test_db_safety


def test_safety_guard_blocks_non_test_db():
    """Verifies that non-test DB name without override raises pytest.exit."""
    with pytest.raises(pytest.exit.Exception) as exc_info:
        check_test_db_safety("production_db")

    assert "SAFETY ABORT" in str(exc_info.value)
    assert "production_db" in str(exc_info.value)


def test_safety_guard_blocks_neondb():
    """Verifies that main database 'neondb' without override raises pytest.exit."""
    with pytest.raises(pytest.exit.Exception) as exc_info:
        check_test_db_safety("neondb")

    assert "SAFETY ABORT" in str(exc_info.value)
    assert "neondb" in str(exc_info.value)


def test_safety_guard_allows_test_db():
    """Verifies that database name containing 'test' passes without error."""
    check_test_db_safety("edunexus_test_p3b4")
    check_test_db_safety("my_test_db")
    check_test_db_safety("TEST_DB")


def test_safety_guard_allows_override(monkeypatch):
    """Verifies that explicit ALLOW_NON_TEST_DB_WRITE matching exact name permits connection."""
    monkeypatch.setenv("ALLOW_NON_TEST_DB_WRITE", "staging_production")
    # Should not raise
    check_test_db_safety("staging_production")

    # Mismatched override still blocked
    with pytest.raises(pytest.exit.Exception):
        check_test_db_safety("other_production_db")

