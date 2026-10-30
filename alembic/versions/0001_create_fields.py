from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # Принудительно удаляем старую таблицу, если она осталась
    op.execute("DROP TABLE IF EXISTS fields CASCADE")
    
    op.create_table(
        "fields",
        sa.Column("field_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column(
            "area_ha", sa.Numeric,
            sa.Computed("ST_Area(geom::geography) / 10000", persisted=True),
            nullable=True,
        ),
    )
    # Строку с op.create_index мы убрали, так как geoalchemy2 делает это сам!

def downgrade():
    op.drop_table("fields")
