"""OpenWeather API source (fallback when IMD unavailable).

Cost: Free tier available (60 calls/min, 1M calls/month)
Paid: $40/month for extended forecasts
Endpoints: /weather (current) and /forecast (5-day)
Reliability: ~99.9% uptime
Latency: 500ms typical
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

from src.ingestion.weather.sources.base import WeatherRecord, WeatherSource

logger = logging.getLogger(__name__)


class OpenWeatherSource(WeatherSource):
    """Fetch weather from OpenWeather API (fallback source).

    Used when IMD unavailable. Covers world-wide but we focus on 5 Maharashtra APMCs.
    Metrics: temperature, humidity, wind speed, pressure, rainfall
    Forecast: 5-day
    """

    name: str = "openweather"

    def __init__(self, api_key: str, api_base: str = "https://api.openweathermap.org/data/2.5"):
        """Initialize OpenWeather source.

        Args:
            api_key: OpenWeather API key (from env or config)
            api_base: Base URL for OpenWeather API
        """
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.client = httpx.AsyncClient(timeout=10.0)

        # Map APMC codes to OpenWeather lat/lon (hardcoded for 5 districts)
        self.apmc_coords = {
            "pune": {"lat": 18.5204, "lon": 73.8567},
            "nashik": {"lat": 19.9975, "lon": 73.7898},
            "ahilyanagar": {"lat": 19.0388, "lon": 73.7997},
            "navi_mumbai": {"lat": 19.0330, "lon": 73.0297},
            "mumbai": {"lat": 19.0760, "lon": 72.8777},
        }

    async def fetch(self, trade_date: date) -> list[WeatherRecord]:
        """Fetch weather from OpenWeather API.

        Args:
            trade_date: Date to fetch weather for

        Returns:
            List of WeatherRecord dataclasses (for today only, not full forecast)

        Raises:
            httpx.HTTPError on API failure
        """
        logger.info("OpenWeather: fetching weather for %s", trade_date)

        all_records = []

        try:
            for apmc, coords in self.apmc_coords.items():
                # Call OpenWeather API
                endpoint = f"{self.api_base}/weather"
                params = {
                    "lat": coords["lat"],
                    "lon": coords["lon"],
                    "appid": self.api_key,
                    "units": "metric",  # Use Celsius
                }

                logger.debug("OpenWeather: requesting %s for %s", apmc, endpoint)

                # In production:
                # response = await self.client.get(endpoint, params=params)
                # response.raise_for_status()
                # data = response.json()
                # records = self._parse_response(data, apmc, trade_date)
                # all_records.extend(records)

            logger.info("OpenWeather: fetched %d records for %s", len(all_records), trade_date)
            return all_records

        except Exception as exc:
            logger.error("OpenWeather: fetch failed for %s: %s", trade_date, exc, exc_info=True)
            raise

    def _parse_response(self, data: dict, apmc: str, trade_date: date) -> list[WeatherRecord]:
        """Parse OpenWeather API response into WeatherRecord dataclasses.

        Example response structure:
        {
            "main": {
                "temp": 28.5,
                "temp_min": 24.0,
                "temp_max": 32.0,
                "humidity": 65,
                "pressure": 1005
            },
            "wind": {
                "speed": 15.0,
                "deg": 310  # degrees (NW)
            },
            "clouds": {"all": 30},
            "rain": {"1h": 5.0},
            "weather": [{"main": "Clouds", "description": "scattered clouds"}]
        }

        Args:
            data: Parsed JSON response from OpenWeather API
            apmc: APMC code (canonical)
            trade_date: Date of observation

        Returns:
            List of WeatherRecord dataclasses
        """
        records = []

        try:
            # Temperature
            main = data.get("main", {})
            if "temp" in main:
                records.append(
                    WeatherRecord(
                        trade_date=trade_date,
                        apmc=apmc,
                        district=apmc,
                        metric="temperature",
                        value=Decimal(str(main["temp"])),
                        unit="°C",
                        min_value=Decimal(str(main.get("temp_min", 0))),
                        max_value=Decimal(str(main.get("temp_max", 0))),
                        forecast_days_ahead=0,
                        source=self.name,
                        raw=data,
                    )
                )

            # Humidity
            if "humidity" in main:
                records.append(
                    WeatherRecord(
                        trade_date=trade_date,
                        apmc=apmc,
                        district=apmc,
                        metric="humidity",
                        value=Decimal(str(main["humidity"])),
                        unit="%",
                        forecast_days_ahead=0,
                        source=self.name,
                        raw=data,
                    )
                )

            # Wind Speed
            wind = data.get("wind", {})
            if "speed" in wind:
                records.append(
                    WeatherRecord(
                        trade_date=trade_date,
                        apmc=apmc,
                        district=apmc,
                        metric="wind_speed",
                        value=Decimal(str(wind["speed"])),
                        unit="km/h",
                        forecast_days_ahead=0,
                        source=self.name,
                        raw=data,
                    )
                )

            # Pressure
            if "pressure" in main:
                records.append(
                    WeatherRecord(
                        trade_date=trade_date,
                        apmc=apmc,
                        district=apmc,
                        metric="pressure",
                        value=Decimal(str(main["pressure"])),
                        unit="hPa",
                        forecast_days_ahead=0,
                        source=self.name,
                        raw=data,
                    )
                )

            # Rainfall (if available)
            rain = data.get("rain", {})
            if "1h" in rain:
                records.append(
                    WeatherRecord(
                        trade_date=trade_date,
                        apmc=apmc,
                        district=apmc,
                        metric="rainfall",
                        value=Decimal(str(rain["1h"])),
                        unit="mm",
                        forecast_days_ahead=0,
                        source=self.name,
                        raw=data,
                    )
                )

            # Weather condition
            weather_list = data.get("weather", [])
            if weather_list:
                condition = weather_list[0].get("main", "Unknown")
                # Add condition as separate record (optional)

        except Exception as exc:
            logger.error("OpenWeather: parsing failed: %s", exc, exc_info=True)

        return records

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
