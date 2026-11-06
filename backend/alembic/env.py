from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (모든 모델을 불러와 SQLModel.metadata에 등록)
from alembic import context
from app.core.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# DB 주소는 alembic.ini가 아니라 앱 설정(.env / 환경변수)에서 가져온다.
# 이렇게 하면 로컬과 배포 환경이 같은 방식으로 주소를 받고, 비밀번호가 파일에 남지 않는다.
_db_url = settings.sqlalchemy_database_url
if not _db_url:
    raise RuntimeError("DATABASE_URL이 설정되지 않았습니다. backend/.env를 확인하세요.")
# alembic은 설정값의 '%'를 특수문자로 해석하므로 '%%'로 바꿔 넣는다. (URL 인코딩된 비밀번호 대비)
config.set_main_option("sqlalchemy.url", _db_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 모델의 테이블 정보. 이것과 실제 DB를 비교해서 마이그레이션을 자동 생성한다.
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(obj, name, type_, reflected, compare_to):
    """DB에는 있지만 우리 모델에는 없는 테이블은 건드리지 않는다.

    이 규칙이 없으면 autogenerate가 '모델에 없는 테이블 = 삭제 대상'으로 보고
    같은 DB에 있는 다른 프로젝트의 테이블을 DROP 하는 마이그레이션을 만든다.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # 컬럼 타입 변경도 감지
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
