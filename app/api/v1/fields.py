import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_AsGeoJSON, ST_GeomFromGeoJSON
from app.core.database import get_session
from app.models.field import Field
from app.schemas.field import FieldCreate, FieldRead

router = APIRouter(prefix="/v1/fields", tags=["fields"])

@router.get("/all")
async def get_all_fields(db: AsyncSession = Depends(get_session)):
    stmt = select(Field)
    result = await db.execute(stmt)
    return result.scalars().all()



@router.post("", response_model=FieldRead, status_code=201)
async def create_field(payload: FieldCreate, db: AsyncSession = Depends(get_session)):
    geom_json = json.dumps(payload.geom)
    stmt = (
        Field.__table__.insert()
        .values(name=payload.name, geom=ST_GeomFromGeoJSON(geom_json))
        .returning(Field.field_id, Field.name, Field.area_ha, ST_AsGeoJSON(Field.geom))
    )
    row = (await db.execute(stmt)).first()
    await db.commit()
    if not row:
        raise HTTPException(500, "insert failed")
    return FieldRead(
        field_id=row[0], name=row[1],
        area_ha=float(row[2]) if row[2] is not None else None,
        geom=json.loads(row[3]),
    )

