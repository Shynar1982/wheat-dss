import ee
import datetime
import json
from sqlalchemy import select, BigInteger, Date, Numeric, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2.functions import ST_AsGeoJSON
from app.models.field import Field
from app.core.database import SessionLocal, Base

class SpectralIndex(Base):
    __tablename__ = "spectral_indices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fields.field_id"))
    observed_at: Mapped[datetime.date] = mapped_column(Date)
    ndvi: Mapped[float] = mapped_column(Numeric(6, 4))
    savi: Mapped[float] = mapped_column(Numeric(6, 4))
    ndwi: Mapped[float] = mapped_column(Numeric(6, 4))
    cloud_cover: Mapped[float] = mapped_column(Numeric(5, 2))
    source: Mapped[str] = mapped_column(String(20))

async def fetch_ndvi_for_field(field_id: int, start_date: str, end_date: str):
    ee.Initialize()
    
    async with SessionLocal() as session:
        stmt = select(Field.name, ST_AsGeoJSON(Field.geom)).where(Field.field_id == field_id)
        row = (await session.execute(stmt)).first()
        if not row:
            print(f"Поле {field_id} не найдено")
            return
        
        name, geom_json = row
        ee_geometry = ee.Geometry(json.loads(geom_json))
        
        s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(ee_geometry)
              .filterDate(start_date, end_date)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
        
        def add_indices(image):
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            ndwi = image.normalizedDifference(['B8', 'B3']).rename('NDWI')
            return image.addBands(ndvi).addBands(ndwi).copyProperties(image, ['system:time_start', 'CLOUDY_PIXEL_PERCENTAGE'])
        
        s2_with_indices = s2.map(add_indices)
        
        def get_stats(image):
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geometry,
                scale=10,
                maxPixels=1e9
            )
            date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
            return ee.Feature(None, {
                'date': date,
                'NDVI': stats.get('NDVI'),
                'NDWI': stats.get('NDWI'),
                'cloud': image.get('CLOUDY_PIXEL_PERCENTAGE')
            })
        
        s2_stats = s2_with_indices.map(get_stats)
        
        try:
            data = s2_stats.getInfo()
            features = data.get('features', [])
            if not features:
                print("За выбранный период нет снимков без облаков.")
                return

            added_count = 0
            for feat in features:
                props = feat.get('properties', {})
                date_str = props.get('date')
                ndvi_val = props.get('NDVI')
                ndwi_val = props.get('NDWI')
                cloud = props.get('cloud')
                
                if ndvi_val is not None and date_str is not None:
                    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    record = SpectralIndex(
                        field_id=field_id, observed_at=dt, ndvi=ndvi_val, 
                        savi=ndvi_val, ndwi=ndwi_val, cloud_cover=cloud, source="Sentinel-2"
                    )
                    session.add(record)
                    added_count += 1
            await session.commit()
            print(f"Успешно добавлено {added_count} записей для поля {field_id}!")
        except Exception as e:
            print(f"Ошибка при запросе к GEE: {e}")