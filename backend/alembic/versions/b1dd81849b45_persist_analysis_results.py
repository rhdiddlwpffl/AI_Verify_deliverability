"""persist analysis results

Revision ID: b1dd81849b45
Revises: 5898c307b134
Create Date: 2026-11-06 09:22:25.063329

분석 결과를 저장하고 그대로 복원하기 위한 변경.
- analyses.anon_token -> anon_token_hash 로 '이름 변경' (토큰 원본이 아니라 SHA-256 해시를 저장)
  (Alembic 자동 생성은 이름 변경을 '삭제 + 추가'로 해석해서 직접 고쳤다. 삭제 + 추가는 데이터를 잃는다)
- 내 기록 목록 조회용 복합 인덱스
- claims: reason, search_status, search_error
- claim_sources: position(검색 결과 순서), downgraded(근거에서 제외됨)
- verifications: error(비교 실패 이유)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes  # SQLModel의 문자열 타입(AutoString)을 쓰는 마이그레이션용


# revision identifiers, used by Alembic.
revision: str = 'b1dd81849b45'
down_revision: Union[str, Sequence[str], None] = '5898c307b134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 이름 변경: 기존 값을 그대로 보존한다.
    op.alter_column('analyses', 'anon_token', new_column_name='anon_token_hash')
    # 단일 컬럼 인덱스는 복합 인덱스(anon_token_hash, created_at)가 대신한다.
    op.drop_index(op.f('ix_analyses_anon_token'), table_name='analyses')
    op.create_index('ix_analyses_anon_created', 'analyses', ['anon_token_hash', 'created_at'], unique=False)

    op.add_column('claims', sa.Column('reason', sa.Text(), nullable=True))
    op.add_column('claims', sa.Column('search_status', sqlmodel.sql.sqltypes.AutoString(), server_default='not_searched', nullable=False))
    op.add_column('claims', sa.Column('search_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('claim_sources', sa.Column('position', sa.Integer(), server_default='0', nullable=False))
    op.add_column('claim_sources', sa.Column('downgraded', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('verifications', sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('verifications', 'error')
    op.drop_column('claim_sources', 'downgraded')
    op.drop_column('claim_sources', 'position')
    op.drop_column('claims', 'search_error')
    op.drop_column('claims', 'search_status')
    op.drop_column('claims', 'reason')

    op.drop_index('ix_analyses_anon_created', table_name='analyses')
    op.alter_column('analyses', 'anon_token_hash', new_column_name='anon_token')
    op.create_index(op.f('ix_analyses_anon_token'), 'analyses', ['anon_token'], unique=False)
