import httpx
from datetime import datetime
import json

# WMO Weather interpretation codes (https://open-meteo.com/en/docs)
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    95: "Thunderstorm"
}

def get_wmo_description(code: int) -> str:
    return WEATHER_CODES.get(code, "Unknown")

def get_weekly_weather(lat: float = 6.45, lon: float = 3.40, timezone: str = "Africa/Lagos") -> str:
    """
    Fetches the 7-day weather forecast from Open-Meteo for the given coordinates.
    Defaults to Lagos, Nigeria (6.45°N, 3.40°E).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone": timezone
    }
    
    try:
        # Use a synchronous client since this might be called inside the LangGraph context node
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            times = daily.get("time", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            precips = daily.get("precipitation_sum", [])
            codes = daily.get("weathercode", [])
            
            if not times:
                return "Weather data unavailable."
                
            forecast = []
            for i in range(len(times)):
                date_str = times[i]
                # Convert date string to day of week
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_name = date_obj.strftime("%A")
                
                desc = get_wmo_description(codes[i])
                max_t = max_temps[i]
                min_t = min_temps[i]
                precip = precips[i]
                
                day_forecast = f"{day_name} ({date_str}): {desc}, High: {max_t}°C, Low: {min_t}°C, Precip: {precip}mm"
                forecast.append(day_forecast)
                
            return "7-Day Weather Forecast (Lagos, Nigeria):\n" + "\n".join(forecast)
            
    except Exception as e:
        print(f"[-] Failed to fetch weather data: {e}")
        return "Weather data unavailable at the moment."
