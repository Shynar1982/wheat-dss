from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "weather_daily",
        sa.Column("field_id", sa.BigInteger, sa.ForeignKey("fields.field_id"), primary_key=True),
        sa.Column("obs_date", sa.Date, primary_key=True),
        sa.Column("t_min_c", sa.Numeric(5, 2)),
        sa.Column("t_max_c", sa.Numeric(5, 2)),
        sa.Column("precip_mm", sa.Numeric(6, 2)),
        sa.Column("gdd_cum", sa.Numeric(8, 2)),
    )

def downgrade():
    op.drop_table("weather_daily")
