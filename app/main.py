from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/health")
async def health():
    return {"status": "ok"}
