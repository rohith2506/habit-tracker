"""remove blocks and block reviews

Drops the Block lifecycle entirely: the blocks and block_reviews tables, plus
the block_id foreign key on goals and habits. Goals and habits become global
per user rather than scoped to an 8-week block.

Revision ID: a7e1b9d4c0f2
Revises: c2af30aeddf3
Create Date: 2026-05-27 00:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7e1b9d4c0f2'
down_revision: Union[str, None] = 'c2af30aeddf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # block_reviews references blocks; drop it before the goals/habits FKs and blocks.
    op.drop_table('block_reviews')

    with op.batch_alter_table('goals', schema=None) as batch_op:
        batch_op.drop_index('ix_goals_block_user')
        batch_op.drop_column('block_id')
        batch_op.create_index('ix_goals_user', ['user_id'], unique=False)

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_index('ix_habits_block_user_status')
        batch_op.drop_column('block_id')
        batch_op.create_index('ix_habits_user_status', ['user_id', 'status'], unique=False)

    op.drop_table('blocks')


def downgrade() -> None:
    op.create_table(
        'blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('length_weeks', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('mid_review_done_at', sa.DateTime(), nullable=True),
        sa.Column('end_review_done_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Re-add as nullable: existing rows have no block to point at on downgrade.
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_index('ix_habits_user_status')
        batch_op.add_column(sa.Column('block_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_habits_block_id', 'blocks', ['block_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.create_index('ix_habits_block_user_status', ['block_id', 'user_id', 'status'], unique=False)

    with op.batch_alter_table('goals', schema=None) as batch_op:
        batch_op.drop_index('ix_goals_user')
        batch_op.add_column(sa.Column('block_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_goals_block_id', 'blocks', ['block_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.create_index('ix_goals_block_user', ['block_id', 'user_id'], unique=False)

    op.create_table(
        'block_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_id', 'user_id', 'kind', name='uq_block_review'),
    )
