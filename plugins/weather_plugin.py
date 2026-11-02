"""
Weather Plugin — demonstrates the plugin system.
Adds weather checking capability to JARVIS.
"""

import os
import requests
from core.plugins import Plugin, VoiceCommandPlugin, PluginInfo, register_plugin


@register_plugin
class WeatherPlugin(VoiceCommandPlugin):
    PLUGIN_INFO = PluginInfo(
        name="weather",
        version="1.0.0",
        description="Check current weather and forecasts",
        author="JARVIS Team",
        dependencies=["requests"],
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "OpenWeatherMap API key"},
                "default_city": {"type": "string", "default": "New York"},
                "units": {"type": "string", "enum": ["metric", "imperial"], "default": "metric"},
                "enabled": {"type": "boolean", "default": True}
            }
        }
    )
    
    COMMAND_ACTIONS = {
        "check_weather": "handle_check_weather",
        "weather_forecast": "handle_forecast",
    }
    
    def __init__(self, jarvis_instance=None):
        super().__init__(jarvis_instance)
        self.api_key = ""
        self.default_city = "New York"
        self.units = "metric"
        self._running = False
    
    def initialize(self) -> bool:
        """Initialize the plugin with configuration."""
        # Get API key from environment or config
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        if not self.api_key:
            print("[Weather] No API key found. Set OPENWEATHER_API_KEY in .env")
            # Don't fail - plugin can still work with limited functionality
        
        # Load from config if available
        cfg = self.config
        if "weather" in cfg.modules:
            mod_cfg = cfg.modules["weather"].config
            self.api_key = mod_cfg.get("api_key", self.api_key)
            self.default_city = mod_cfg.get("default_city", self.default_city)
            self.units = mod_cfg.get("units", self.units)
        
        return True
    
    def start(self) -> bool:
        self._running = True
        return True
    
    def stop(self) -> bool:
        self._running = False
        return True
    
    def get_summary(self) -> str:
        return f"🌤 Weather: {'Ready' if self.api_key else 'No API key'}"
    
    def handle_check_weather(self, command: str, action: dict) -> bool:
        """Handle 'check weather' command."""
        city = action.get("city") or action.get("location") or self.default_city
        weather = self._get_current_weather(city)
        
        if weather:
            temp = weather["main"]["temp"]
            desc = weather["weather"][0]["description"]
            feels = weather["main"]["feels_like"]
            humidity = weather["main"]["humidity"]
            
            unit_symbol = "°C" if self.units == "metric" else "°F"
            response = (f"Current weather in {city}: {desc.capitalize()}, "
                       f"{temp}{unit_symbol} (feels like {feels}{unit_symbol}), "
                       f"humidity {humidity}%")
        else:
            response = f"Couldn't get weather for {city}."
        
        self.jarvis._say(response)
        return True
    
    def handle_forecast(self, command: str, action: dict) -> bool:
        """Handle weather forecast command."""
        city = action.get("city") or action.get("location") or self.default_city
        forecast = self._get_forecast(city)
        
        if forecast:
            lines = [f"3-day forecast for {city}:"]
            for day in forecast[:3]:
                dt = day["dt"]
                temp = day["main"]["temp"]
                desc = day["weather"][0]["description"]
                lines.append(f"  {dt}: {desc.capitalize()}, {temp}{'°C' if self.units == 'metric' else '°F'}")
            response = "\n".join(lines)
        else:
            response = f"Couldn't get forecast for {city}."
        
        self.jarvis._say(response)
        return True
    
    def _get_current_weather(self, city: str) -> dict:
        """Fetch current weather from OpenWeatherMap."""
        if not self.api_key:
            return None
        
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": self.units,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[Weather] Error fetching weather: {e}")
            return None
    
    def _get_forecast(self, city: str) -> list:
        """Fetch 3-day forecast from OpenWeatherMap."""
        if not self.api_key:
            return None
        
        try:
            url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": self.units,
                "cnt": 24,  # 3 days * 8 (3-hour intervals)
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            # Group by day
            from collections import defaultdict
            from datetime import datetime
            
            daily = defaultdict(list)
            for item in data["list"]:
                date = datetime.fromtimestamp(item["dt"]).date()
                daily[date].append(item)
            
            # Get one entry per day (midday)
            forecast = []
            for date, items in sorted(daily.items())[:3]:
                midday = min(items, key=lambda x: abs(datetime.fromtimestamp(x["dt"]).hour - 12))
                forecast.append(midday)
            
            return forecast
        except Exception as e:
            print(f"[Weather] Error fetching forecast: {e}")
            return None


# Example: Simple calculator plugin
@register_plugin
class CalculatorPlugin(VoiceCommandPlugin):
    PLUGIN_INFO = PluginInfo(
        name="calculator",
        version="1.0.0",
        description="Basic calculator operations",
        author="JARVIS Team",
        dependencies=[],
        config_schema={"type": "object", "properties": {"enabled": {"type": "boolean", "default": True}}}
    )
    
    COMMAND_ACTIONS = {
        "calculate": "handle_calculate",
    }
    
    def initialize(self) -> bool:
        return True
    
    def start(self) -> bool:
        return True
    
    def stop(self) -> bool:
        return True
    
    def get_summary(self) -> str:
        return "🧮 Calculator: Ready"
    
    def handle_calculate(self, command: str, action: dict) -> bool:
        """Handle calculation requests."""
        expression = action.get("expression") or action.get("message", "")
        
        # Extract math expression from command
        import re
        # Simple extraction - in practice you'd use the brain to parse
        math_expr = re.search(r'[\d\+\-\*\/\(\)\.\s]+', expression)
        if math_expr:
            expr = math_expr.group().strip()
            try:
                # Safe evaluation - only allow basic math
                allowed = set('0123456789+-*/(). ')
                if all(c in allowed for c in expr):
                    result = eval(expr)
                    self.jarvis._say(f"The answer is {result}")
                else:
                    self.jarvis._say("I can only do basic arithmetic.")
            except Exception:
                self.jarvis._say("I couldn't calculate that.")
        else:
            self.jarvis._say("What would you like me to calculate?")
        
        return True