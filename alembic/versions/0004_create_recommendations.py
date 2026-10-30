from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "recommendations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("field_id", sa.BigInteger, sa.ForeignKey("fields.field_id"), nullable=False),
        sa.Column("rec_type", sa.String(50), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

def downgrade():
    op.drop_table("recommendations")
