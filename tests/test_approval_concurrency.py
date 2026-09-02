from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.core.errors import ApprovalStateConflictError
from app.db.session import SessionLocal
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services.approval import ApprovalService
from app.tools.system import build_default_tool_registry


def test_concurrent_approve_executes_exact_action_once() -> None:
    setup = SessionLocal()
    requester_id = uuid4()
    target_id = uuid4()
    approval_id = uuid4()

    try:
        admin_role = setup.scalar(
            select(Role).where(
                Role.name == "admin"
            )
        )
        support_role = setup.scalar(
            select(Role).where(
                Role.name == "support_agent"
            )
        )
        assert admin_role is not None
        assert support_role is not None

        requester = User(
            id=requester_id,
            email=f"approval-admin-{requester_id}@example.com",
            display_name="Approval Admin",
        )
        target = User(
            id=target_id,
            email=f"approval-target-{target_id}@example.com",
            display_name="Approval Target",
        )
        setup.add_all(
            [
                requester,
                target,
            ]
        )
        setup.flush()
        setup.add(
            UserRole(
                user_id=requester_id,
                role_id=admin_role.id,
            )
        )
        setup.add(
            ApprovalRequest(
                id=approval_id,
                requested_by_user_id=requester_id,
                tool_name="grant_support_agent_role",
                tool_arguments={
                    "user_id": str(target_id),
                },
                status="pending",
                expires_at=(
                    datetime.now(timezone.utc)
                    + timedelta(minutes=15)
                ),
            )
        )
        setup.commit()

        barrier = Barrier(2)

        def decide() -> str:
            session = SessionLocal()
            try:
                service = ApprovalService(
                    session,
                    build_default_tool_registry(),
                )
                barrier.wait(timeout=10)
                service.approve(
                    approval_id=approval_id,
                    approver_user_id=requester_id,
                )
                return "executed"
            except ApprovalStateConflictError:
                return "conflict"
            finally:
                session.close()

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            outcomes = list(
                executor.map(
                    lambda _: decide(),
                    range(2),
                )
            )

        assert sorted(outcomes) == [
            "conflict",
            "executed",
        ]

        setup.expire_all()
        approval = setup.get(
            ApprovalRequest,
            approval_id,
        )
        assert approval is not None
        assert approval.status == "executed"

        assignment_count = setup.scalar(
            select(func.count())
            .select_from(UserRole)
            .where(
                UserRole.user_id == target_id,
                UserRole.role_id == support_role.id,
            )
        )
        assert assignment_count == 1

    finally:
        setup.rollback()
        setup.execute(
            delete(AuditEvent).where(
                AuditEvent.actor_user_id
                == requester_id
            )
        )
        setup.execute(
            delete(ApprovalRequest).where(
                ApprovalRequest.id
                == approval_id
            )
        )
        setup.execute(
            delete(UserRole).where(
                UserRole.user_id.in_(
                    [
                        requester_id,
                        target_id,
                    ]
                )
            )
        )
        setup.execute(
            delete(User).where(
                User.id.in_(
                    [
                        requester_id,
                        target_id,
                    ]
                )
            )
        )
        setup.commit()
        setup.close()
