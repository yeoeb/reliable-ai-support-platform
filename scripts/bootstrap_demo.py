from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or reuse a development-only local demo administrator "
            "and seed deterministic Knowledge documents."
        )
    )
    parser.add_argument(
        "--email",
        help="Administrator email; prompted when omitted.",
    )
    parser.add_argument(
        "--display-name",
        default="Local Demo Administrator",
        help="Display name used only when a new administrator is created.",
    )
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help=(
            "Promote an existing authenticated non-admin account. "
            "Without this flag the bootstrap refuses promotion."
        ),
    )
    parser.add_argument(
        "--enable-live-ai",
        action="store_true",
        help=(
            "Create live OpenAI embeddings for seeded documents. "
            "This is disabled by default and may incur cost."
        ),
    )
    return parser


def _print_result(result: object) -> None:
    administrator_created = getattr(result, "administrator_created")
    role_changed = getattr(result, "admin_role_changed")
    knowledge = getattr(result, "knowledge")
    live_ai_enabled = getattr(result, "live_ai_enabled")

    created_documents = sum(item.changed for item in knowledge)
    embedded_documents = sum(item.embedded for item in knowledge)

    print("Local demo bootstrap completed.")
    print(
        "Administrator: "
        + ("created" if administrator_created else "authenticated and reused")
    )
    print("Administrator user ID: " + str(getattr(result, "administrator_user_id")))
    print(
        "Admin role: "
        + ("assigned" if role_changed else "already assigned")
    )
    print(
        f"Knowledge: {len(knowledge)} seeded "
        f"({created_documents} created, "
        f"{len(knowledge) - created_documents} reused)"
    )
    if live_ai_enabled:
        print(
            f"Live AI: enabled; {embedded_documents} documents embedded. "
            "Retrieval and grounded RAG are available through authorized APIs."
        )
    else:
        print(
            "Live AI: disabled; no Provider calls were made. "
            "Health, Auth, RBAC, Audit, Knowledge, Tool, Approval, and metrics "
            "APIs remain available."
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))

    try:
        from app.core.config import settings
        from app.core.errors import InvalidCredentialsError
        from app.db.session import SessionLocal
        from app.integrations.embeddings import OpenAIEmbeddingProvider
        from app.schemas.user import UserCreate
        from app.services.demo_bootstrap import (
            DemoBootstrapError,
            DemoBootstrapService,
            load_demo_knowledge,
        )
    except Exception:
        print(
            "Demo bootstrap configuration could not be loaded.",
            file=sys.stderr,
        )
        return 1

    if settings.app_env.strip().lower() != "development":
        print(
            "Demo bootstrap is allowed only in development.",
            file=sys.stderr,
        )
        return 1

    provider = None
    if args.enable_live_ai:
        api_key = (
            settings.openai_api_key.get_secret_value().strip()
            if settings.openai_api_key is not None
            else ""
        )
        if not api_key:
            print(
                "Live AI was requested, but OPENAI_API_KEY is not configured.",
                file=sys.stderr,
            )
            return 1
        provider = OpenAIEmbeddingProvider(
            api_key=api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    try:
        email = args.email or input("Administrator email: ").strip()
        password = getpass.getpass("Administrator password: ")
        administrator = UserCreate(
            email=email,
            display_name=args.display_name,
            password=password,
        )
        knowledge_seeds = load_demo_knowledge(
            REPOSITORY_ROOT / "demo" / "knowledge"
        )

        with SessionLocal() as session:
            service = DemoBootstrapService(
                session,
                app_env=settings.app_env,
                embedding_provider=provider,
                embedding_model=settings.embedding_model,
                embedding_dimensions=settings.embedding_dimensions,
                embedding_batch_size=settings.embedding_batch_size,
                chunk_size=settings.knowledge_chunk_size,
                chunk_overlap=settings.knowledge_chunk_overlap,
            )
            result = service.bootstrap(
                administrator=administrator,
                knowledge_seeds=knowledge_seeds,
                promote_existing=args.promote_existing,
                enable_live_ai=args.enable_live_ai,
            )
    except ValidationError:
        print(
            "Administrator input is invalid. Use a valid email, a non-empty "
            "display name, and a password between 12 and 128 characters.",
            file=sys.stderr,
        )
        return 1
    except InvalidCredentialsError:
        print(
            "Existing administrator authentication failed.",
            file=sys.stderr,
        )
        return 1
    except DemoBootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print(
            "Demo bootstrap failed. Review the redacted application logs.",
            file=sys.stderr,
        )
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
