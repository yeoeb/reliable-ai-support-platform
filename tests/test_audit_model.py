from app.db.base import Base
from app.models import AuditEvent


def test_audit_event_table_schema() -> None:
    table = AuditEvent.__table__

    assert "audit_events" in Base.metadata.tables
    assert set(table.columns.keys()) == {
        "id",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "outcome",
        "occurred_at",
        "metadata",
    }
    assert not table.foreign_keys
    assert table.c.id.primary_key is True
    assert table.c.actor_user_id.nullable is True


def test_audit_event_uses_non_reserved_python_metadata_attribute() -> None:
    assert hasattr(AuditEvent, "event_metadata")
    assert not hasattr(AuditEvent, "metadata") or AuditEvent.metadata is Base.metadata
