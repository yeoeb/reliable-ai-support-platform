from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def get_script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    return ScriptDirectory.from_config(config)


def test_alembic_config_exists() -> None:
    assert ALEMBIC_INI.exists()


def test_alembic_script_directory_loads() -> None:
    script = get_script_directory()

    assert script.dir is not None


def test_migration_history_is_not_empty() -> None:
    script = get_script_directory()

    revisions = list(script.walk_revisions())

    assert revisions


def test_alembic_has_single_head() -> None:
    script = get_script_directory()

    heads = script.get_heads()

    assert len(heads) == 1


def test_head_revision_has_upgrade_and_downgrade() -> None:
    script = get_script_directory()

    head_revision = script.get_current_head()
    assert head_revision is not None

    migration_script = script.get_revision(head_revision)
    assert migration_script is not None

    module = migration_script.module

    assert callable(module.upgrade)
    assert callable(module.downgrade)