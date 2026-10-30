from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "spectral_indices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("field_id", sa.BigInteger, sa.ForeignKey("fields.field_id"), nullable=False),
        sa.Column("observed_at", sa.Date, nullable=False),
        sa.Column("ndvi", sa.Numeric(6, 4)),
        sa.Column("savi", sa.Numeric(6, 4)),
        sa.Column("ndwi", sa.Numeric(6, 4)),
        sa.Column("cloud_cover", sa.Numeric(5, 2)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.UniqueConstraint("field_id", "observed_at", "source", name="uq_field_date_source")
    )
    op.create_index("idx_spectral_field_time", "spectral_indices", ["field_id", "observed_at"])

def downgrade():
    op.drop_table("spectral_indices")
