import os
from datetime import datetime, timedelta
from sentinelhub import (
    SHConfig, SentinelHubStatistical, DataCollection, CRS, Geometry
)

config = SHConfig()
config.sh_client_id = os.getenv("SH_CLIENT_ID")
config.sh_client_secret = os.getenv("SH_CLIENT_SECRET")
# Настройки для Copernicus Data Space Ecosystem
config.sh_base_url = "https://sh.dataspace.copernicus.eu"
config.sh_auth_base_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

def get_live_ndvi(geom_dict):
    sh_geometry = Geometry(geom_dict, crs=CRS.WGS84)
    
    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input: [{ bands: ["B04", "B08", "dataMask"] }],
            output: [
                { id: "ndvi", bands: 1 },
                { id: "dataMask", bands: 1 }
            ]
        };
    }
    function evaluatePixel(samples) {
        let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
        return {
            data: [ndvi],
            dataMask: [samples.dataMask]
        };
    }
    """

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)

    aggregation = SentinelHubStatistical.aggregation(
        evalscript=evalscript,
        time_interval=(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")),
        aggregation_interval="P1D",
        size=[512, 512]
    )

    request = SentinelHubStatistical(
        aggregation=aggregation,
        input_data=[
            SentinelHubStatistical.input_data(
                DataCollection.SENTINEL2_L2A,
                maxcc=0.3 # Максимальная облачность 30%
            )
        ],
        geometry=sh_geometry,
        config=config
    )

    response = request.get_data()
    
    results = []
    for entry in response:
        for data_entry in entry['data']:
            date_str = data_entry['interval']['from']
            stats = data_entry['outputs']['ndvi']['bands']['B0']['stats']
            if stats and 'mean' in stats and stats['mean'] is not None:
                results.append({
                    "observed_at": date_str.split('T')[0],
                    "ndvi": round(stats['mean'], 3)
                })
    return results
