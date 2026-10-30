from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    # Таблица для обучения (прошлые годы)
    op.create_table(
        "historical_yield",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("field_id", sa.BigInteger, sa.ForeignKey("fields.field_id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("yield_t_ha", sa.Numeric(6, 3), nullable=False)
    )
    # Таблица для прогнозов
    op.create_table(
        "yield_predictions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("field_id", sa.BigInteger, sa.ForeignKey("fields.field_id"), nullable=False),
        sa.Column("prediction_date", sa.Date, server_default=sa.text('CURRENT_DATE')),
        sa.Column("predicted_yield_t_ha", sa.Numeric(6, 3), nullable=False),
        sa.Column("model_version", sa.String(50))
    )

def downgrade():
    op.drop_table("yield_predictions")
    op.drop_table("historical_yield")
