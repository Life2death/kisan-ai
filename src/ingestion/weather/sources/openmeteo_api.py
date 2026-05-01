"""Open-Meteo weather data source (Phase 2 Module 1).

Open-Meteo is a free, open-source weather API with no authentication required.

API: https://api.open-meteo.com/v1/forecast
Cost: Free (no API key needed)
Coverage: Global (all Maharashtra talukas via lat/lon)
Metrics: temperature (2m), precipitation, relative_humidity_2m, wind_speed_10m, pressure_msl
Forecast: Today + next 7 days
Latency: <1 second per request
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

from src.ingestion.weather.sources.base import WeatherRecord, WeatherSource

logger = logging.getLogger(__name__)

# Maharashtra taluka coordinates (lat, lon)
_TALUKA_COORDS = {
    "ahmednagar": (19.0952, 74.7480),
    "rahata": (18.8833, 74.5833),
    "kopargaon": (19.2500, 74.4833),
    "sangamner": (19.0500, 74.2667),
    "akole": (19.0667, 74.0333),
    "shrigonda": (18.9667, 74.5333),
    "shevgaon": (19.1167, 74.6500),
    "pathardi": (18.9667, 74.8333),
    "nevasa": (19.2000, 74.8667),
    "rahuri": (18.8667, 74.7167),
    "jamkhed": (18.9833, 74.8500),
    "karjat_a": (18.8000, 74.6500),
    "parner": (18.9500, 74.2667),
    "goregaon_parner": (19.0916, 74.4742),
    "wadegaon_parner": (18.5561, 74.0658),
    "pune": (18.5204, 73.8567),
    "nashik": (19.9975, 73.7898),
    "navi_mumbai": (19.0330, 73.0297),
    "mumbai": (19.0760, 72.8777),
}


class OpenMeteoWeatherSource(WeatherSource):
    """Fetch weather observations from Open-Meteo.

    Covers: All Maharashtra talukas (via lat/lon)
    Metrics: temperature, precipitation, humidity, wind_speed, pressure
    Forecast: Today + next 7 days
    """

    name: str = "openmeteo"

    def __init__(self, api_url: str = "https://api.open-meteo.com/v1/forecast"):
        """Initialize Open-Meteo source.

        Args:
            api_url: Base URL for Open-Meteo API (default: production)
        """
        self.api_url = api_url
        self.client = httpx.AsyncClient(timeout=15.0)

    async def fetch(self, trade_date: date) -> list[WeatherRecord]:
        """Fetch weather observations from Open-Meteo for a given date.

        Returns observations + forecasts for all Maharashtra talukas.

        Args:
            trade_date: Date to fetch weather for (YYYY-MM-DD)

        Returns:
            List of WeatherRecord dataclasses
        """
        logger.info("OpenMeteo: fetching weather for %s", trade_date)
        all_records = []

        try:
            # Fetch data for each taluka in parallel
            for taluka, (lat, lon) in _TALUKA_COORDS.items():
                try:
                    records = await self._fetch_taluka(taluka, lat, lon, trade_date)
                    all_records.extend(records)
                except Exception as exc:
                    logger.warning("OpenMeteo: fetch failed for %s: %s", taluka, exc)
                    continue

            logger.info("OpenMeteo: fetched %d records for %s", len(all_records), trade_date)
            return all_records

        except Exception as exc:
            logger.error("OpenMeteo: fetch failed for %s: %s", trade_date, exc, exc_info=True)
            return []

    async def _fetch_taluka(self, taluka: str, lat: float, lon: float, trade_date: date) -> list[WeatherRecord]:
        """Fetch weather for a single taluka from Open-Meteo.

        Args:
            taluka: Taluka slug (e.g., "ahmednagar")
            lat: Latitude
            lon: Longitude
            trade_date: Date to fetch for

        Returns:
            List of WeatherRecord dataclasses
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,pressure_msl",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "pressure_unit": "hPa",
            "timezone": "Asia/Kolkata",
        }

        response = await self.client.get(self.api_url, params=params)
        response.raise_for_status()
        data = response.json()

        records = []

        # Parse current conditions
        if "current" in data:
            current = data["current"]
            records.extend(self._parse_current(taluka, trade_date, current))

        # Parse daily data
        if "daily" in data:
            daily = data["daily"]
            records.extend(self._parse_daily(taluka, trade_date, daily))

        return records

    def _parse_current(self, taluka: str, trade_date: date, current: dict) -> list[WeatherRecord]:
        """Parse current conditions from Open-Meteo."""
        records = []

        # Map taluka to district
        district = self._get_district(taluka)

        # Temperature
        if "temperature_2m" in current and current["temperature_2m"] is not None:
            records.append(
                WeatherRecord(
                    trade_date=trade_date,
                    apmc=taluka,
                    district=district,
                    metric="temperature",
                    value=Decimal(str(current["temperature_2m"])),
                    unit="°C",
                    forecast_days_ahead=0,
                    source=self.name,
                    condition=self._weather_code_to_condition(current.get("weather_code")),
                    raw=current,
                )
            )

        # Humidity
        if "relative_humidity_2m" in current and current["relative_humidity_2m"] is not None:
            records.append(
                WeatherRecord(
                    trade_date=trade_date,
                    apmc=taluka,
                    district=district,
                    metric="humidity",
                    value=Decimal(str(current["relative_humidity_2m"])),
                    unit="%",
                    forecast_days_ahead=0,
                    source=self.name,
                    raw=current,
                )
            )

        # Wind Speed
        if "wind_speed_10m" in current and current["wind_speed_10m"] is not None:
            records.append(
                WeatherRecord(
                    trade_date=trade_date,
                    apmc=taluka,
                    district=district,
                    metric="wind_speed",
                    value=Decimal(str(current["wind_speed_10m"])),
                    unit="km/h",
                    forecast_days_ahead=0,
                    source=self.name,
                    raw=current,
                )
            )

        # Pressure
        if "pressure_msl" in current and current["pressure_msl"] is not None:
            records.append(
                WeatherRecord(
                    trade_date=trade_date,
                    apmc=taluka,
                    district=district,
                    metric="pressure",
                    value=Decimal(str(current["pressure_msl"])),
                    unit="hPa",
                    forecast_days_ahead=0,
                    source=self.name,
                    raw=current,
                )
            )

        return records

    def _parse_daily(self, taluka: str, trade_date: date, daily: dict) -> list[WeatherRecord]:
        """Parse daily data from Open-Meteo."""
        records = []
        district = self._get_district(taluka)

        dates = daily.get("time", [])
        temps_max = daily.get("temperature_2m_max", [])
        temps_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        humidity = daily.get("relative_humidity_2m_max", [])

        for i, date_str in enumerate(dates):
            forecast_date = date.fromisoformat(date_str)
            days_ahead = (forecast_date - trade_date).days

            if days_ahead < 0 or days_ahead > 7:
                continue

            # Max temperature
            if i < len(temps_max) and temps_max[i] is not None:
                records.append(
                    WeatherRecord(
                        trade_date=forecast_date,
                        apmc=taluka,
                        district=district,
                        metric="temperature",
                        value=Decimal(str(temps_max[i])),
                        unit="°C",
                        min_value=Decimal(str(temps_min[i])) if i < len(temps_min) and temps_min[i] is not None else None,
                        max_value=Decimal(str(temps_max[i])),
                        forecast_days_ahead=days_ahead,
                        source=self.name,
                        raw=daily,
                    )
                )

            # Precipitation (rainfall)
            if i < len(precip) and precip[i] is not None:
                records.append(
                    WeatherRecord(
                        trade_date=forecast_date,
                        apmc=taluka,
                        district=district,
                        metric="rainfall",
                        value=Decimal(str(precip[i])),
                        unit="mm",
                        forecast_days_ahead=days_ahead,
                        source=self.name,
                        raw=daily,
                    )
                )

        return records

    @staticmethod
    def _get_district(taluka: str) -> str:
        """Map taluka to parent district."""
        district_map = {
            "ahmednagar": "ahilyanagar",
            "rahata": "ahilyanagar",
            "kopargaon": "ahilyanagar",
            "sangamner": "ahilyanagar",
            "akole": "ahilyanagar",
            "shrigonda": "ahilyanagar",
            "shevgaon": "ahilyanagar",
            "pathardi": "ahilyanagar",
            "nevasa": "ahilyanagar",
            "rahuri": "ahilyanagar",
            "jamkhed": "ahilyanagar",
            "karjat_a": "ahilyanagar",
            "parner": "ahilyanagar",
            "goregaon_parner": "ahilyanagar",
            "wadegaon_parner": "ahilyanagar",
        }
        return district_map.get(taluka, taluka)

    @staticmethod
    def _weather_code_to_condition(code: Optional[int]) -> str:
        """Map WMO weather code to condition description."""
        if code is None:
            return ""

        code_map = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Freezing fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Thunderstorm with hail",
        }
        return code_map.get(code, "Unknown")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            import asyncio
            asyncio.run(self.close())
        except Exception:
            pass
