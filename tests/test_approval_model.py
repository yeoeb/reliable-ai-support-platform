from sqlalchemy.dialects.postgresql import JSONB

from app.models.approval_request import ApprovalRequest


def test_approval_request_schema_contract() -> None:
    table = ApprovalRequest.__table__

    assert table.name == "approval_requests"
    assert table.c.requested_by_user_id.nullable is False
    assert table.c.tool_name.type.length == 100
    assert isinstance(
        table.c.arguments.type,
        JSONB,
    )
    assert table.c.status.type.length == 20
    assert table.c.expires_at.nullable is False
    assert table.c.decided_by_user_id.nullable is True
    assert table.c.decided_at.nullable is True
    assert table.c.executed_at.nullable is True

    assert not table.c.requested_by_user_id.foreign_keys
    assert not table.c.decided_by_user_id.foreign_keys
