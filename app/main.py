from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_AsGeoJSON

from app.core.database import get_session
from app.models.field import Field

from app.api.v1.fields import router as fields_router
from app.api.v1.indices import router as indices_router
from app.api.v1.weather import router as weather_router
from app.api.v1.recommendations import router as rec_router
from app.api.v1.predictions import router as pred_router
from app.api.v1.sms import router as sms_router

app = FastAPI(title="Wheat DSS", version="0.1.0")
templates = Jinja2Templates(directory="app/templates")

app.include_router(fields_router)
app.include_router(indices_router)
app.include_router(weather_router)
app.include_router(rec_router)
app.include_router(pred_router)
app.include_router(sms_router)

@app.get("/api/all-fields")
async def get_all_fields_direct(db: AsyncSession = Depends(get_session)):
    # Берем только нужные колонки, а геометрию превращаем в строку GeoJSON
    stmt = select(
        Field.field_id,
        Field.name,
        Field.area_ha,
        ST_AsGeoJSON(Field.geom).label("geom")
    )
    result = await db.execute(stmt)
    # result.mappings() отдаст словари, которые FastAPI без проблем сериализует в JSON
    return [dict(row) for row in result.mappings().all()]

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/health")
async def health():
    return {"status": "ok"}
