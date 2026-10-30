from sqlalchemy import BigInteger, String, Computed
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
from app.core.database import Base

class Field(Base):
    __tablename__ = "fields"

    field_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    area_ha: Mapped[float] = mapped_column(
        Computed("ST_Area(geom::geography) / 10000", persisted=True),
        nullable=True,
    )
