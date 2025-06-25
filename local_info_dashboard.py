# local_info_dashboard.py
# This Streamlit application provides real-time local insights
# including weather, news, and an interactive map for a specified location.

import streamlit as st
import requests
import pandas as pd
import folium # For interactive maps
from folium.plugins import MarkerCluster # For clustering markers on the map
import json # To parse JSON responses sometimes needed
import datetime # For handling timestamps for day/night calculation
import time # Added for getting the current live timestamp
import random # For simulating ML outputs

# --- Configuration ---
PAGE_TITLE = "Local Insights Dashboard"
LAYOUT = "wide"
INITIAL_SIDEBAR_STATE = "expanded" # Keep sidebar open by default for navigation

# --- API Keys (Replace with your actual keys!) ---
# You need to register for free API keys from these services.
# NewsAPI: https://newsapi.org/
NEWS_API_KEY = "3560896cacd64d4bbf8ba279e94163ad" # Replace with your NewsAPI key

# OpenWeatherMap: https://openweathermap.org/
OPENWEATHER_API_KEY = "76455df0e04d5b883f417d724f7052ca" # Replace with your OpenWeatherMap API key

# --- API Endpoints ---
NEWS_API_BASE_URL = "https://newsapi.org/v2/top-headlines"
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_REVERSE_GEO_URL = "http://api.openweathermap.org/geo/1.0/reverse" 

# --- Global Country Code Mappings ---
# NewsAPI expects 2-letter ISO country codes.
# This dictionary maps full country names to their ISO 2-letter codes.
COUNTRY_NAME_TO_ISO = {
    'United States': 'us', 'Canada': 'ca', 'United Kingdom': 'gb',
    'Australia': 'au', 'Germany': 'de', 'France': 'fr',
    'South Africa': 'za', 'India': 'in', 'Brazil': 'br',
    'China': 'cn', 'Japan': 'jp', 'Mexico': 'mx', 'Nigeria': 'ng',
    'Egypt': 'eg', 'Ireland': 'ie', 'Italy': 'it', 'Netherlands': 'nl',
    'New Zealand': 'nz', 'Norway': 'no', 'Philippines': 'ph',
    'Poland': 'pl', 'Portugal': 'pt', 'Romania': 'ro', 'Russia': 'ru',
    'Saudi Arabia': 'sa', 'Serbia': 'rs', 'Singapore': 'sg',
    'Slovakia': 'sk', 'Slovenia': 'si', 'South Korea': 'kr',
    'Sweden': 'se', 'Switzerland': 'ch', 'Taiwan': 'tw',
    'Thailand': 'th', 'Turkey': 'tr', 'Ukraine': 'ua',
    'United Arab Emirates': 'ae', 'Venezuela': 've',
    # Add more mappings as needed for countries you expect users to input
}

# Reverse mapping from ISO codes to full country names, for display purposes if needed
ISO_TO_FULL_COUNTRY_NAME = {v: k for k, v in COUNTRY_NAME_TO_ISO.items()}


# --- Initialize session state for inputs (ALL SESSION STATE VARIABLES MUST BE INITIALIZED HERE) ---
if 'city_input' not in st.session_state:
    st.session_state.city_input = "" # Start empty for auto-detection
if 'country_input' not in st.session_state:
    st.session_state.country_input = "" # Start empty for auto-detection
if 'news_query_term' not in st.session_state:
    st.session_state.news_query_term = ""
if 'geolocation_attempted' not in st.session_state:
    st.session_state.geolocation_attempted = False # Not yet attempted
if 'geolocation_coords' not in st.session_state:
    st.session_state.geolocation_coords = None
if 'initial_location_set' not in st.session_state:
    st.session_state.initial_location_set = False # Needs to be set by detection
if 'insights_triggered' not in st.session_state:
    st.session_state.insights_triggered = False # Not triggered until location is set
if 'geolocation_detected' not in st.session_state: # New state variable for geolocation status
    st.session_state.geolocation_detected = False

# --- Helper Functions (Defined at the top to ensure they are available) ---

@st.cache_data(ttl=600) # Cache weather data for 10 minutes
def get_weather(city: str, country: str, api_key: str):
    """
    Fetches current weather data for a given city and country.
    
    Args:
        city (str): Name of the city.
        country (str): Name of the country.
        api_key (str): OpenWeatherMap API key.
        
    Returns:
        dict: Weather data, or None if an error occurs.
    """
    params = {
        "q": f"{city},{country}",
        "appid": api_key,
        "units": "metric" # Get temperatures in Celsius
    }
    try:
        response = requests.get(OPENWEATHER_BASE_URL, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching weather data: {e}. Please check the city/country spelling and your OpenWeatherMap API key. Also, ensure your API key is active (may take a few hours after creation) and you are within your free plan's rate limits.)")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Error decoding weather API response: {e}")
        return None

@st.cache_data(ttl=3600) # Cache geocoding results for an hour (kept for completeness if needed)
def get_city_country_from_coords(lat: float, lon: float, api_key: str):
    """
    Reverse geocodes coordinates to get city and country names.
    Returns city name and ISO 2-letter country code.
    """
    params = {
        "lat": lat,
        "lon": lon,
        "limit": 1, # Get the most relevant result
        "appid": api_key
    }
    try:
        response = requests.get(OPENWEATHER_REVERSE_GEO_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            city = data[0].get('name')
            country_iso = data[0].get('country') # This is the ISO 2-letter code
            return city, country_iso
        return None, None
    except requests.exceptions.RequestException as e:
        st.error(f"Error reverse geocoding: {e}")
        return None, None

def get_day_night_and_local_time(current_timestamp, sunrise_timestamp, sunset_timestamp, timezone_offset_seconds):
    tz_delta = datetime.timedelta(seconds=timezone_offset_seconds)
    tz_info = datetime.timezone(tz_delta)

    # current_timestamp is expected to be a Unix timestamp (UTC)
    current_dt_local = datetime.datetime.fromtimestamp(current_timestamp, tz=tz_info)
    sunrise_dt_local = datetime.datetime.fromtimestamp(sunrise_timestamp, tz=tz_info)
    sunset_dt_local = datetime.datetime.fromtimestamp(sunset_timestamp, tz=tz_info)

    day_night_status = "Daytime ☀️" if sunrise_dt_local <= current_dt_local <= sunset_dt_local else "Nighttime 🌙"
    
    # Calculate day length
    day_length_seconds = (sunset_dt_local - sunrise_dt_local).total_seconds()
    day_length_hours = int(day_length_seconds // 3600)
    day_length_minutes = int((day_length_seconds % 3600) // 60)
    day_length_str = f"{day_length_hours}h {day_length_minutes}m"

    return day_night_status, current_dt_local.strftime('%H:%M %p'), day_length_str, sunrise_dt_local.strftime('%H:%M %p'), sunset_dt_local.strftime('%H:%M %p')

def get_wind_direction(deg):
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / (360. / len(directions)))
    return directions[idx % len(directions)]

def get_weather_emoji(main_weather):
    main_weather = main_weather.lower()
    if "clear" in main_weather:
        return "☀️"
    elif "cloud" in main_weather:
        return "☁️"
    elif "rain" in main_weather or "drizzle" in main_weather:
        return "🌧️"
    elif "thunderstorm" in main_weather:
        return "⛈️"
    elif "snow" in main_weather:
        return "❄️"
    elif "mist" in main_weather or "fog" in main_weather or "haze" in main_weather:
        return "🌫️"
    else:
        return "🌡️" # Default emoji

def get_innovative_weather_suggestions(temp, description, wind_speed, humidity, is_day, pressure, visibility):
    suggestions = {
        "👕 Dress Code": "",
        "🤸 Activity Idea": "",
        "❤️ Health Tip": "",
        "🚗 Commute Ready": "",
        "💡 Energy Savvy": "",
        "🌿 Green Thumb": "",
        "🐶 Pet Pal": "",
        "💧 Stay Hydrated": "",
        "😎 Sun Safety": "",
        "🌬️ Wind Advisory": "",
        "🌈 Mood Boost": ""
    }

    # Temperature-based advice
    if temp < 5: # Freezing
        suggestions["👕 Dress Code"] = "Heavy coat, hat, gloves. Layers are key!"
        suggestions["🤸 Activity Idea"] = "Indoor games, cozy reading, or snowman building (if snow!)."
        suggestions["❤️ Health Tip"] = "Beware of ice! Limit exposed skin. Hypothermia risk."
    elif 5 <= temp < 15: # Cool
        suggestions["👕 Dress Code"] = "Light jacket or sweater. Smart to layer."
        suggestions["🤸 Activity Idea"] = "Museum visits, coffee shop hopping, or a brisk walk."
    elif 15 <= temp < 25: # Mild
        suggestions["👕 Dress Code"] = "Comfortable light clothing. Long-sleeves for evenings."
        suggestions["🤸 Activity Idea"] = "Outdoor sports, picnic, or exploring local sights."
        suggestions["❤️ Health Tip"] = "Sunscreen is vital if sunny. Drink water!"
    elif 25 <= temp < 30: # Warm
        suggestions["👕 Dress Code"] = "Shorts and t-shirt. Breathable fabrics."
        suggestions["🤸 Activity Idea"] = "Beach day, swimming, or outdoor dining (in shade)."
        suggestions["❤️ Health Tip"] = "Hydrate constantly! Watch for heat exhaustion."
    else: # Hot (temp >= 30)
        suggestions["👕 Dress Code"] = "Lightest clothing. Avoid dark colors."
        suggestions["🤸 Activity Idea"] = "Indoor pools, air-conditioned places, or early/late outdoor walks."
        suggestions["❤️ Health Tip"] = "Extreme heat! Stay indoors, drink lots of water, check on others."

    # Condition-based refinements
    weather_desc = description.lower()
    if "rain" in weather_desc or "drizzle" in weather_desc:
        suggestions["👕 Dress Code"] += " Umbrella/waterproof jacket needed!"
        suggestions["🤸 Activity Idea"] = "Movies, board games, or indoor shopping."
        suggestions["🚗 Commute Ready"] = "Slippery roads. Drive slow, increase distance."
        suggestions["🌿 Green Thumb"] = "Plants love it! Collect rainwater."
        suggestions["🐶 Pet Pal"] = "Wipe paws after walks. Keep pets dry."
        suggestions["🌈 Mood Boost"] = "Cozy up with a warm drink and a good book!"
    elif "snow" in weather_desc:
        suggestions["👕 Dress Code"] += " Snow boots, waterproof gear!"
        suggestions["🤸 Activity Idea"] = "Snowball fight, building a snowman, or relaxing indoors."
        suggestions["🚗 Commute Ready"] = "Icy/snowy roads. Drive with care or use public transport."
        suggestions["🐶 Pet Pal"] = "Limit pet outdoor time, protect paws."
        suggestions["🌈 Mood Boost"] = "Enjoy the winter wonderland from inside!"
    elif "fog" in weather_desc or "mist" in weather_desc or "haze" in weather_desc:
        suggestions["🚗 Commute Ready"] = "Low visibility. Use headlights, drive slowly."
        suggestions["❤️ Health Tip"] = "Be extra cautious when walking/driving. Use fog lights."
        suggestions["🌈 Mood Boost"] = "A mysterious, quiet day. Perfect for reflection."
    elif "clear" in weather_desc and is_day:
        suggestions["❤️ Health Tip"] += " High UV! Reapply sunscreen often."
        suggestions["😎 Sun Safety"] = "Wear sunglasses and a hat. Seek shade between 10 AM - 4 PM."
    elif "clear" in weather_desc and not is_day:
        suggestions["🤸 Activity Idea"] = "Fantastic for stargazing or night photography! ✨"
    elif "cloud" in weather_desc:
        suggestions["💡 Energy Savvy"] = "Good day for natural light, reduce indoor lighting."
        suggestions["🌈 Mood Boost"] = "A mellow day. Perfect for indoor hobbies or gentle walks."

    if wind_speed > 10: # Strong wind
        suggestions["👕 Dress Code"] += " Windproof layers!"
        suggestions["🤸 Activity Idea"] = "Avoid windy sports (e.g., kite flying, exposed cycling)."
        suggestions["🚗 Commute Ready"] = "Strong gusts can affect tall vehicles. Watch for debris."
        suggestions["🌬️ Wind Advisory"] = "Secure loose outdoor items. Stay cautious near tall structures."

    # Pressure-based insights (simple, direct)
    if isinstance(pressure, (int, float)):
        if pressure < 1000: # Low pressure
            suggestions["❤️ Health Tip"] += " Low pressure can sometimes cause headaches for sensitive people."
            suggestions["🤸 Activity Idea"] += " You might feel sluggish. Relaxing activities are best."
        elif pressure > 1020: # High pressure
            suggestions["💡 Energy Savvy"] += " Stable weather. Great for opening windows to air out rooms."

    # Visibility-based insights
    if isinstance(visibility, (int, float)) and visibility < 5000: # Less than 5km
        suggestions["🚗 Commute Ready"] = "Reduced visibility. Drive slower and increase following distance."
        suggestions["❤️ Health Tip"] += " Be extra alert when outdoors."
    
    # Hydration Tip (always relevant, but emphasized in heat)
    if temp >= 25 or humidity >= 70:
        suggestions["💧 Stay Hydrated"] = "Drink plenty of water throughout the day!"
    else:
        suggestions["💧 Stay Hydrated"] = "Keep a water bottle handy and sip regularly."

    # General Pet Care Tip
    if temp < 10:
        suggestions["🐾 Pet Pal"] += " Consider warm bedding for outdoor pets."
    elif temp > 28:
        suggestions["🐾 Pet Pal"] += " Ensure pets have plenty of fresh water and shade."

    # Remove empty suggestions for cleaner display
    return {k: v for k, v in suggestions.items() if v}


@st.cache_data(ttl=300) # Cache news data for 5 minutes
def get_news(query: str, country_name: str, api_key: str):
    """
    Fetches top news headlines for a given query and country.
    Handles both full country names and ISO 2-letter codes for the country.
    
    Args:
        query (str): Search query (e.g., city name or topic). Can be empty.
        country_name (str): Full name of the country (e.g., 'South Africa') or ISO 2-letter code (e.g., 'ZA').
        api_key (str): NewsAPI key.
        
    Returns:
        list: List of news articles, or empty list if an error occurs.
    """
    if not api_key or api_key == "YOUR_NEWS_API_KEY":
        st.error("NewsAPI key is not configured. Please set `NEWS_API_KEY`.")
        return []

    iso_country_code = None
    # Check if the input country_name is already a 2-letter ISO code
    if len(country_name) == 2 and country_name.isalpha():
        iso_country_code = country_name.lower()
    else:
        # Try to map full country name to ISO code
        iso_country_code = COUNTRY_NAME_TO_ISO.get(country_name.title(), None)

    if not iso_country_code:
        # Get the original full name for the warning message
        display_country_name = ISO_TO_FULL_COUNTRY_NAME.get(country_name.lower(), country_name)
        st.warning(f"Could not determine 2-letter country code for '{display_country_name}'. NewsAPI 'top-headlines' endpoint requires a valid country code. Attempting to fetch with country code 'us' as a fallback, but results may not be relevant.")
        iso_country_code = 'us' # Fallback to US if country code not found

    params = {
        "apiKey": api_key,
        "pageSize": 5, # Limit to 5 headlines
        "country": iso_country_code # Country is required for top-headlines
    }
    
    if query: # Only add 'q' parameter if a query term is provided
        params["q"] = query

    try:
        response = requests.get(NEWS_API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and data.get("articles"):
            return data["articles"]
        return []
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching news data: {e}. Please check your NewsAPI key, internet connection, or try a different country/query. NewsAPI's free tier has limitations, including strict rate limits and may not provide hyper-local news.")
        return []
    except json.JSONDecodeError as e:
        st.error(f"Error decoding news API response: {e}")
        return []

# --- NLP/Transformer-based News Summary and Sentiment (SIMULATED) ---
def get_news_summary_and_sentiment(articles: list):
    """
    Simulates NLP/Transformer-based news summarization and sentiment analysis.
    In a real application, this would use an actual NLP model (e.g., Hugging Face Transformers).
    """
    summaries = []
    sentiments = []
    
    for article in articles:
        text_to_process = article.get('description', article.get('content', ''))
        if not text_to_process:
            summaries.append("No summary available.")
            sentiments.append("Neutral")
            continue

        # Simulate summarization (very basic, takes first 2 sentences)
        sentences = text_to_process.split('.')
        summary = ". ".join(sentences[:2]) + ("..." if len(sentences) > 2 else "")
        summaries.append(summary.strip())
        
        # Simulate sentiment analysis
        sentiment_score = random.uniform(-1, 1) # Random score between -1 and 1
        if sentiment_score > 0.3:
            sentiments.append("Positive 😊")
        elif sentiment_score < -0.3:
            sentiments.append("Negative 😠")
        else:
            sentiments.append("Neutral 😐")
            
    return summaries, sentiments


# --- Public Transport Status Helper Function ---
def get_public_transport_status(city: str, country: str):
    """
    Simulates fetching real-time public transport status for a given city and country.
    In a real application, this would integrate with specific public transport APIs
    (e.g., city transit authority APIs, GTFS-Realtime feeds).
    
    Returns a list of dictionaries, each representing a public transport line's status.
    """
    # Use .lower() for case-insensitive comparison
    if city.lower() == "berea" and country.lower() == "south africa":
        return [
            {"line": "Durban People Mover", "status": "On Time", "details": "Normal service.", "color": "green"},
            {"line": "Metrorail: Kwa-Zulu Natal", "status": "Delayed", "details": "Minor delays (5-10 min) due to signal fault near Durban Station.", "color": "orange"},
            {"line": "Bus Rapid Transit (Go!Durban)", "status": "On Time", "details": "Running as scheduled.", "color": "green"}
        ]
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return [
            {"line": "MyCiTi Bus: Table View Express (T01)", "status": "On Time", "details": "Normal service.", "color": "green"},
            {"line": "Metrorail: Southern Line", "status": "Delayed", "details": "Minor delays (10-15 min) due to signal fault near Rondebosch.", "color": "orange"},
            {"line": "MyCiTi Bus: Airport Shuttle (A01)", "status": "On Time", "details": "Running as scheduled to Cape Town International Airport.", "color": "green"},
            {"line": "Metrorail: Central Line", "status": "Service Disruption", "details": "Partial closure between Langa and Philippi. Shuttle buses operating.", "color": "red"},
            {"line": "Golden Arrow Bus: Route 123 (City Bowl to Gardens)", "status": "Minor Delay", "details": "Expect 5 min delay due to increased traffic.", "color": "orange"}
        ]
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return [
            {"line": "London Underground: Piccadilly Line", "status": "Good Service", "details": "No reported delays.", "color": "green"},
            {"line": "London Underground: Central Line", "status": "Minor Delays", "details": "Minor delays due to earlier signal failure at Leytonstone.", "color": "orange"},
            {"line": "London Overground: East London Line", "status": "Part Suspended", "details": "No service between New Cross Gate and Crystal Palace.", "color": "red"},
            {"line": "London Bus: Route 38 (Victoria to Clapton)", "status": "On Time", "details": "Normal schedule.", "color": "green"}
        ]
    else:
        return [] # No simulated data for other locations

# --- Local Events Helper Function ---
def get_local_events(city: str, country: str):
    """
    Simulates fetching upcoming local events and activities for a given city and country.
    In a real application, this would integrate with event APIs (e.g., Eventbrite, local tourism board APIs).
    
    Returns a list of dictionaries, each representing an event.
    """
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    next_week = today + datetime.timedelta(weeks=1)

    if city.lower() == "berea" and country.lower() == "south africa":
        return [
            {
                "title": "Florida Road Street Market",
                "date": today.strftime('%Y-%m-%d'),
                "time": "10:00 AM - 04:00 PM",
                "location": "Florida Road, Morningside",
                "description": "Local crafts, food stalls, and live music.",
                "link": "https://example.com/florida-market"
            },
            {
                "title": "Botanical Gardens Bird Walk",
                "date": tomorrow.strftime('%Y-%m-%d'),
                "time": "07:00 AM",
                "location": "Durban Botanic Gardens",
                "description": "Guided bird watching tour, bring binoculars!",
                "link": "https://example.com/bird-walk"
            },
            {
                "title": "Quiz Night at The Taphouse",
                "date": next_week.strftime('%Y-%m-%d'),
                "time": "07:30 PM",
                "location": "The Taphouse, Berea",
                "description": "Weekly quiz night, great food and prizes.",
                "link": "https://example.com/quiz-night"
            }
        ]
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return [
            {
                "title": "Local Farmers Market",
                "date": today.strftime('%Y-%m-%d'),
                "time": "09:00 AM - 02:00 PM",
                "location": "Company's Garden",
                "description": "Fresh produce, artisanal goods, and local crafts.",
                "link": "https://example.com/farmers-market"
            },
            {
                "title": "Sunset Concert at Kirstenbosch",
                "date": tomorrow.strftime('%Y-%m-%d'),
                "time": "06:00 PM",
                "location": "Kirstenbosch National Botanical Garden",
                "description": "Enjoy live music against the backdrop of Table Mountain.",
                "link": "https://example.com/kirstenbosch-concerts"
            },
            {
                "title": "Art Exhibition: 'Cape Town Through My Lens'",
                "date": next_week.strftime('%Y-%m-%d'),
                "time": "10:00 AM - 05:00 PM",
                "location": "Iziko South African National Gallery",
                "description": "A collection of contemporary photography showcasing Cape Town's vibrancy.",
                "link": "https://example.com/art-exhibition"
            }
        ]
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return [
            {
                "title": "West End Theatre Show: 'Hamilton'",
                "date": today.strftime('%Y-%m-%d'),
                "time": "07:30 PM",
                "location": "Victoria Palace Theatre",
                "description": "Experience the critically acclaimed musical.",
                "link": "https://example.com/hamilton-london"
            },
            {
                "title": "British Museum Guided Tour",
                "date": tomorrow.strftime('%Y-%m-%d'),
                "time": "11:00 AM",
                "location": "British Museum",
                "description": "Discover world history and culture.",
                "link": "https://example.com/british-museum-tours"
            },
            {
                "title": "Food Festival: 'Taste of London'",
                "date": next_week.strftime('%Y-%m-%d'),
                "time": "12:00 PM - 09:00 PM",
                "location": "Regent's Park",
                "description": "Sample culinary delights from London's best restaurants.",
                "link": "https://example.com/taste-of-london"
            }
        ]
    else:
        return [] # No simulated data for other locations

# --- Environmental Health Data Helper Function ---
def get_environmental_health_data(city: str, country: str):
    """
    Simulates fetching environmental health data (e.g., Air Quality Index, Pollen)
    for a given city and country.
    
    Returns a dictionary with AQI and Pollen information.
    """
    if city.lower() == "berea" and country.lower() == "south africa":
        return {
            "air_quality": {
                "aqi": 45,
                "status": "Good",
                "pollutants": "PM2.5, SO2",
                "advice": "Air quality is good. Enjoy outdoor activities! Check local updates if sensitive."
            },
            "pollen": {
                "level": "Moderate",
                "type": "Grass, Weeds",
                "advice": "Pollen levels are moderate. Allergy sufferers may experience mild symptoms."
            },
            "uv_index": {
                "value": 6,
                "status": "High",
                "advice": "High UV index. Wear sunscreen (SPF 30+), sunglasses, and a hat. Seek shade between 10 AM - 4 PM."
            }
        }
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return {
            "air_quality": {
                "aqi": 35,
                "status": "Good",
                "pollutants": "PM2.5, Ozone",
                "advice": "Air quality is good. Enjoy outdoor activities! Check local updates if sensitive."
            },
            "pollen": {
                "level": "Low",
                "type": "Grass, Tree",
                "advice": "Pollen levels are low. Most individuals should experience minimal symptoms."
            },
            "uv_index": {
                "value": 7,
                "status": "High",
                "advice": "High UV index. Wear sunscreen (SPF 30+), sunglasses, and a hat. Seek shade between 10 AM - 4 PM."
            }
        }
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return {
            "air_quality": {
                "aqi": 55,
                "status": "Moderate",
                "pollutants": "PM10, NO2",
                "advice": "Air quality is moderate. Sensitive groups should consider reducing prolonged outdoor exertion."
            },
            "pollen": {
                "level": "Moderate",
                "type": "Grass, Birch",
                "advice": "Moderate pollen levels. Allergy sufferers may experience symptoms. Consider taking antihistamines."
            },
            "uv_index": {
                "value": 4,
                "status": "Moderate",
                "advice": "Moderate UV index. Sun protection is recommended, especially for prolonged outdoor exposure."
            }
        }
    else:
        return None # No simulated data

# --- Nearby Businesses Helper Function ---
def get_nearby_businesses(city: str, country: str):
    """
    Simulates fetching information about nearby businesses (malls, shops, services)
    for a given city and country.
    
    Returns a list of dictionaries, each representing a business.
    """
    if city.lower() == "berea" and country.lower() == "south africa":
        return [
            {
                "name": "Musgrave Centre",
                "type": "Shopping Mall",
                "address": "115 Musgrave Rd, Berea, Durban",
                "hours": "09:00 AM - 06:00 PM (Mon-Sat), 10:00 AM - 04:00 PM (Sun)",
                "status": "Open",
                "link": "https://www.musgravecentre.co.za/"
            },
            {
                "name": "Medicross Berea",
                "type": "Medical Centre/Pharmacy",
                "address": "48 Problem Mkhize Rd, Berea, Durban",
                "hours": "07:00 AM - 07:00 PM (Mon-Fri), 08:00 AM - 04:00 PM (Sat-Sun)",
                "status": "Open",
                "link": "https://www.medicross.co.za/"
            },
            {
                "name": "African Art Centre",
                "type": "Art Gallery/Shop",
                "address": "94 Florida Rd, Morningside, Durban",
                "hours": "09:00 AM - 05:00 PM (Mon-Fri), 09:00 AM - 01:00 PM (Sat)",
                "status": "Open",
                "link": "https://www.afriartcentre.co.za/"
            }
        ]
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return [
            {
                "name": "V&A Waterfront",
                "type": "Shopping Mall",
                "address": "Dock Rd, Victoria & Alfred Waterfront, Cape Town",
                "hours": "09:00 AM - 09:00 PM (Daily)",
                "status": "Open",
                "link": "https://www.waterfront.co.za/"
            },
            {
                "name": "Clicks Pharmacy (Long Street)",
                "type": "Pharmacy",
                "address": "151 Long St, Cape Town City Centre",
                "hours": "08:00 AM - 06:00 PM (Mon-Fri), 09:00 AM - 02:00 PM (Sat)",
                "status": "Open",
                "link": "https://www.clicks.co.za/"
            },
            {
                "name": "The Test Kitchen (Temporarily Closed)",
                "type": "Restaurant",
                "address": "The Old Biscuit Mill, 375 Albert Rd, Woodstock",
                "hours": "N/A",
                "status": "Closed",
                "link": "https://www.thetestkitchen.co.za/"
            }
        ]
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return [
            {
                "name": "Westfield London",
                "type": "Shopping Mall",
                "address": "Ariel Way, Shepherd's Bush, London W12 7GF",
                "hours": "10:00 AM - 10:00 PM (Mon-Sat), 12:00 PM - 06:00 PM (Sun)",
                "status": "Open",
                "link": "https://uk.westfield.com/london"
            },
            {
                "name": "Boots Pharmacy (Oxford Street)",
                "type": "Pharmacy",
                "address": "433 Oxford St, London W1C 2AP",
                "hours": "09:00 AM - 09:00 PM (Daily)",
                "status": "Open",
                "link": "https://www.boots.com/"
            },
            {
                "name": "Dishoom Covent Garden",
                "type": "Restaurant",
                "address": "12 Upper St. Martin's Lane, London WC2H 9FB",
                "hours": "08:00 AM - 11:00 PM (Mon-Fri), 09:00 AM - 11:00 PM (Sat-Sun)",
                "status": "Open",
                "link": "https://www.dishoom.com/covent-garden"
            }
        ]
    else:
        return [] # No simulated data

# --- Community Resources Helper Function ---
def get_community_resources(city: str, country: str):
    """
    Simulates fetching information about local community resources.
    """
    if city.lower() == "berea" and country.lower() == "south africa":
        return [
            {
                "name": "Denis Hurley Centre",
                "type": "Homeless Support",
                "details": "Provides food, shelter, and medical care for the homeless.",
                "link": "https://denishurleycentre.org/"
            },
            {
                "name": "Durban Central Library",
                "type": "Library & Education",
                "details": "Offers free books, internet access, and community programs.",
                "link": "https://www.durban.gov.za/City_Services/Library_Services/Pages/default.aspx"
            },
            {
                "name": "SA Human Rights Commission (KZN Office)",
                "type": "Legal & Rights",
                "details": "Investigates human rights violations and provides legal advice.",
                "link": "https://www.sahrc.org.za/"
            }
        ]
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return [
            {
                "name": "Cape Town Food Bank",
                "type": "Food Assistance",
                "details": "Provides food aid to vulnerable communities. Check website for distribution points.",
                "link": "https://example.com/capetown-foodbank"
            },
            {
                "name": "Cape Town Public Library (Central)",
                "type": "Library & Education",
                "details": "Offers free books, internet access, and community workshops.",
                "link": "https://example.com/capetown-library"
            },
            {
                "name": "Legal Aid South Africa (Cape Town Office)",
                "type": "Legal Services",
                "details": "Provides legal assistance to those who cannot afford it.",
                "link": "https://www.legal-aid.co.za/"
            }
        ]
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return [
            {
                "name": "The Trussell Trust (London Food Banks)",
                "type": "Food Assistance",
                "details": "Network of food banks providing emergency food and support.",
                "link": "https://www.trusselltrust.org/"
            },
            {
                "name": "British Library",
                "type": "Library & Education",
                "details": "The national library of the United Kingdom, offering vast collections and events.",
                "link": "https://www.bl.uk/"
            },
            {
                "name": "Citizens Advice (London)",
                "type": "Legal & Advice",
                "details": "Free, confidential advice on legal, debt, consumer, and other problems.",
                "link": "https://www.citizensadvice.org.uk/london/"
            }
        ]
    else:
        return []

# --- Sustainability Initiatives Helper Function ---
def get_sustainability_initiatives(city: str, country: str):
    """
    Simulates fetching information about local sustainability and environmental initiatives.
    """
    if city.lower() == "berea" and country.lower() == "south africa":
        return [
            {
                "name": "Durban Green Corridor",
                "type": "Environmental Conservation",
                "details": "Projects focused on preserving natural areas and promoting eco-tourism.",
                "link": "https://durbangreencorridor.co.za/"
            },
            {
                "name": "eThekwini Municipality Recycling Programme",
                "type": "Waste Management",
                "details": "Information on household recycling, drop-off sites, and waste separation guidelines.",
                "link": "https://www.durban.gov.za/City_Services/waste_management/Pages/default.aspx"
            },
            {
                "name": "Rainwater Harvesting Workshop (Local NPO)",
                "type": "Water Management",
                "details": "Learn how to install and maintain rainwater harvesting systems for your home. Next session: 15 July.",
                "link": "https://example.com/rainwater-workshop"
            }
        ]
    elif city.lower() == "cape town" and country.lower() == "south africa":
        return [
            {
                "name": "Waste Collection Schedule",
                "type": "Waste Management",
                "details": "Your next recycling collection is Tuesday. General waste is Friday.",
                "link": "https://www.capetown.gov.za/City-Connect/Waste-and-recycling/Waste-collection-services"
            },
            {
                "name": "Water Conservation Tips",
                "type": "Water Management",
                "details": "High water-saving efforts still encouraged. Keep showers short.",
                "link": "https://www.capetown.gov.za/City-Connect/Apply/Municipal-services/Water-and-sanitation-services/water-conservation-tips"
            },
            {
                "name": "Urban Greening Project: Bo-Kaap Community Garden",
                "type": "Urban Farming",
                "details": "Volunteer sessions every Saturday 10 AM. All welcome to help cultivate fresh produce.",
                "link": "https://example.com/bokaap-garden"
            }
        ]
    elif city.lower() == "london" and country.lower() == "united kingdom":
        return [
            {
                "name": "Recycling Service Updates (London Boroughs)",
                "type": "Waste Management",
                "details": "Check your local borough's website for specific collection days and recycling rules.",
                "link": "https://www.london.gov.uk/what-we-do/environment/waste-and-recycling"
            },
            {
                "name": "Thames Water Smart Meter Program",
                "type": "Water Management",
                "details": "Sign up for a smart meter to track usage and save water.",
                "link": "https://www.thameswater.co.uk/my-account/water-meter/smart-meters"
            },
            {
                "name": "London Community Gardens Directory",
                "type": "Urban Farming",
                "details": "Find a community garden near you to grow your own food or volunteer.",
                "link": "https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/london-environment-strategy/food/community-food-growing"
            }
        ]
    else:
        return []

# --- Traffic Prediction (SIMULATED ML) ---
def predict_traffic_congestion(city: str, current_time: str, weather_condition: str):
    """
    Simulates an ML model predicting traffic congestion level.
    In a real scenario, this would use a trained model with real-time data.
    """
    if city.lower() == "berea":
        if "rain" in weather_condition.lower() and ("07:00 AM" <= current_time <= "09:00 AM" or "04:00 PM" <= current_time <= "06:00 PM"):
            return "High 🔴 (Expected heavy rain and peak hour)"
        elif "clear" in weather_condition.lower() and ("07:00 AM" <= current_time <= "09:00 AM" or "04:00 PM" <= current_time <= "06:00 PM"):
            return "Moderate 🟠 (Typical peak hour congestion)"
        else:
            return "Low 🟢 (Normal flow)"
    elif city.lower() == "cape town":
        if "rain" in weather_condition.lower() and ("07:00 AM" <= current_time <= "09:00 AM" or "04:00 PM" <= current_time <= "06:00 PM"):
            return "High 🔴 (Expected heavy rain and peak hour)"
        elif "clear" in weather_condition.lower() and ("07:00 AM" <= current_time <= "09:00 AM" or "04:00 PM" <= current_time <= "06:00 PM"):
            return "Moderate 🟠 (Typical peak hour congestion)"
        else:
            return "Low 🟢 (Normal flow)"
    elif city.lower() == "london":
        if "rain" in weather_condition.lower() and ("07:00 AM" <= current_time <= "10:00 AM" or "04:00 PM" <= current_time <= "07:00 PM"):
            return "Very High 🔴 (Dense city traffic, expect severe delays)"
        elif ("07:00 AM" <= current_time <= "10:00 AM" or "04:00 PM" <= current_time <= "07:00 PM"):
            return "High 🔴 (Standard London peak traffic)"
        else:
            return "Moderate 🟠 (General city movement)"
    return "Unknown ⚪ (No data for this city)"

# --- Personalized Deal Recommendation (SIMULATED ML) ---
def get_deal_recommendations(city: str, weather_condition: str, current_events: list):
    """
    Simulates an ML model providing personalized deal recommendations.
    This would involve a recommendation engine.
    """
    recommendations = []
    
    if city.lower() == "berea":
        if "rain" in weather_condition.lower():
            recommendations.append("☔ 10% off at **Book Boutique** (Umhlanga) with any hot beverage.")
            recommendations.append("🍽️ 15% off at **Lupa Osteria** (Florida Road) for indoor dining.")
        else:
            recommendations.append("🏖️ Free beach towel with purchase at **Surf Zone** (North Beach).")
            recommendations.append("🍦 2-for-1 ice cream at **The Waffle House** (Southbroom).")
        if any("market" in e['title'].lower() for e in current_events):
            recommendations.append("🛍️ Special discount at stalls at **Florida Road Street Market**.")
    elif city.lower() == "cape town":
        if "rain" in weather_condition.lower():
            recommendations.append("☔ 20% off at **The Book Lounge** (cozy reading!)")
            recommendations.append("☕ Buy one get one free coffee at **Truth Coffee Roasting**.")
        else:
            recommendations.append("☀️ 15% off **Table Mountain Cableway** tickets.")
            recommendations.append("🍦 Free scoop with any large ice cream at **The Creamery**.")

        if any("concert" in e['title'].lower() for e in current_events):
            recommendations.append("🍔 Special: Pre-concert dinner discount at nearby restaurants!")
            
    elif city.lower() == "london":
        if "rain" in weather_condition.lower():
            recommendations.append("🎭 Discounted theatre tickets for evening shows.")
            recommendations.append("📖 Half-price admission to **British Library** exhibitions.")
        else:
            recommendations.append("🚶‍♀️ Walking tour discount: 'Hidden Gems of London'.")
            recommendations.append("🍺 Happy Hour deals at pubs in Covent Garden.")

        if any("festival" in e['title'].lower() for e in current_events):
            recommendations.append("🎟️ Exclusive festival passes available!")

    if not recommendations:
        return ["No special recommendations available right now."]
    return recommendations


# --- Function to simulate geolocation and update state ---
def simulate_geolocation_and_update_state(api_key):
    """
    Simulates fetching geolocation and updates session state with the detected city/country.
    In a real application, this would involve client-side JavaScript.
    """
    # Simulate a set of coordinates for Berea, KwaZulu-Natal, South Africa
    simulated_lat = -29.8587
    simulated_lon = 31.0218

    # Use OpenWeatherMap's reverse geocoding to get city/country (ISO code) from simulated coords
    detected_city, detected_country_iso = get_city_country_from_coords(simulated_lat, simulated_lon, api_key)

    if detected_city and detected_country_iso:
        # Convert ISO code to full country name for display and consistent internal use
        detected_country_full_name = ISO_TO_FULL_COUNTRY_NAME.get(detected_country_iso.upper(), detected_country_iso)
        
        st.session_state.city_input = detected_city
        st.session_state.country_input = detected_country_full_name
        st.session_state.insights_triggered = True
        st.session_state.geolocation_detected = True
        st.rerun() # Rerun the app to apply the new location
    else:
        st.sidebar.error("Could not detect location automatically. Please enter manually.")
        st.session_state.geolocation_detected = False

# --- End of Helper Functions ---


# --- 1. Dashboard Configuration and Title ---
st.set_page_config(
    page_title=PAGE_TITLE,
    layout=LAYOUT,
    initial_sidebar_state=INITIAL_SIDEBAR_STATE
)

st.title("📍 Local Insights Dashboard")
st.markdown("---")

# --- Initial Geolocation Detection on Load ---
# This block attempts to simulate geolocation once per session or until explicitly set.
if not st.session_state.geolocation_detected and not st.session_state.initial_location_set:
    if OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
        st.warning("OpenWeatherMap API Key is not configured. Cannot auto-detect location. Please set `OPENWEATHER_API_KEY` in the code or enter location manually.")
        st.session_state.geolocation_detected = True # Mark as attempted to avoid endless loop
        st.session_state.initial_location_set = True # Assume manual path if API key is missing
    else:
        with st.spinner("Attempting to auto-detect your location..."):
            simulate_geolocation_and_update_state(OPENWEATHER_API_KEY)
            # If simulate_geolocation_and_update_state reruns, this part won't be reached
            # If it doesn't rerun (e.g., API error), then geolocation_detected will be False,
            # and the user will see manual input fields.
    st.session_state.initial_location_set = True # Ensure this block runs only once for initial setup


# --- Introduction and User Guide ---
st.info(
    """
    **Welcome!** Get instant local weather, top news, and an interactive map.

    **How to use:**
    1.  Location is **auto-detected** (simulated) on load.
    2.  Change **City/Country** and **News Search** in the sidebar.
    3.  Click **'Get Local Insights!'** to update.

    *Remember to put your real API keys in the code for full features!*
    """
)
st.markdown("---")


# --- 2. Sidebar for Location Input and News Query ---
st.sidebar.header("🗺️ Your Location & News Preferences")
st.sidebar.write("Enter the city and country for which you want to get insights.")

# Input fields for city and country using session state
# Pre-populate with detected values if available, otherwise keep empty for manual input
current_city_val = st.session_state.city_input if st.session_state.geolocation_detected else st.session_state.city_input
current_country_val = st.session_state.country_input if st.session_state.geolocation_detected else st.session_state.country_input

st.session_state.city_input = st.sidebar.text_input("City:", value=current_city_val, help="E.g., London, New York", key="sidebar_city_input")
st.session_state.country_input = st.sidebar.text_input("Country:", value=current_country_val, help="E.g., United States, South Africa", key="sidebar_country_input")

st.sidebar.markdown("---")
# Removed "Detect My Current Location" button as it's now automatic

st.sidebar.write("Optional: Filter news headlines.")
st.session_state.news_query_term = st.sidebar.text_input("News Search Term (Optional):", value=st.session_state.news_query_term, help="e.g., 'local politics', 'sports', 'economy'. Leave empty for general headlines.", key="sidebar_news_query")

# Button to trigger data fetch (explicitly set insights_triggered)
if st.sidebar.button("Get Local Insights! 🔄"):
    st.session_state.insights_triggered = True
    st.session_state.geolocation_detected = True # If user manually clicks, consider location set
    # Clear cache when explicitly fetching new insights
    st.cache_data.clear()


# Add the auto-refresh checkbox
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ App Settings")
auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh (every 60 seconds)", value=False, help="Automatically refreshes the dashboard to fetch updated data and time.")


# These warnings are crucial for API key setup
if not NEWS_API_KEY or NEWS_API_KEY == "YOUR_NEWS_API_KEY":
    st.sidebar.warning("Please replace 'YOUR_NEWS_API_KEY' in the code with your actual NewsAPI key.")
if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
    st.sidebar.warning("Please replace 'YOUR_OPENWEATHER_API_KEY' in the code with your actual OpenWeatherMap API key.")


# --- 4. Main Content Display ---
# Only proceed with fetching and displaying insights if location is detected or explicitly provided
if st.session_state.insights_triggered and st.session_state.city_input and st.session_state.country_input:
    city_to_fetch = st.session_state.city_input
    country_to_fetch = st.session_state.country_input
    news_query_to_fetch = st.session_state.news_query_term

    if NEWS_API_KEY == "YOUR_NEWS_API_KEY" or OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
        st.error("API keys are not configured. Please update `NEWS_API_KEY` and `OPENWEATHER_API_KEY` in the code.")
    else:
        st.subheader(f"Insights for {city_to_fetch}, {country_to_fetch}")
        
        # Fetch data that multiple tabs might need
        weather_data = get_weather(city_to_fetch, country_to_fetch, OPENWEATHER_API_KEY)
        news_articles = get_news(news_query_to_fetch, country_to_fetch, NEWS_API_KEY)
        transport_data = get_public_transport_status(city_to_fetch, country_to_fetch)
        events_data = get_local_events(city_to_fetch, country_to_fetch)
        env_health_data = get_environmental_health_data(city_to_fetch, country_to_fetch)
        nearby_businesses_data = get_nearby_businesses(city_to_fetch, country_to_fetch)

        # Create tabs for different sections, including the new "Intelligent Insights"
        tab_weather, tab_news, tab_transport, tab_events, tab_env_health, tab_nearby_places, tab_community, tab_sustainability, tab_intelligent_insights, tab_map, tab_future_ideas = st.tabs([
            "☀️ Weather", "📰 News", "🚌 Transport", "🗓️ Events", "🌳 Health", "🛍️ Nearby", "🤝 Community", "♻️ Eco-Info", "🧠 Insights", "🗺️ Map", "💡 Future Ideas"
        ])

        # --- Tab 1: Weather Section ---
        with tab_weather:
            st.header("☀️ Current Weather Snapshot")
            with st.spinner(f"Fetching weather data for {city_to_fetch}..."):
                if weather_data:
                    temp = weather_data['main']['temp']
                    feels_like = weather_data['main']['feels_like']
                    description = weather_data['weather'][0]['description']
                    humidity = weather_data['main']['humidity']
                    wind_speed = weather_data['wind']['speed']
                    wind_deg = weather_data['wind'].get('deg', 'N/A') # Wind direction in degrees
                    pressure = weather_data['main']['pressure'] # New: Pressure
                    visibility = weather_data.get('visibility', 'N/A') # Visibility in meters
                    main_weather_condition = weather_data['weather'][0]['main'] # e.g., "Clear", "Clouds"
                    cloudiness = weather_data['clouds']['all'] # New: Cloudiness percentage
                    
                    # Get the current live Unix timestamp for accurate local time
                    current_live_timestamp = time.time()

                    # Get day/night indicator and local time using the live timestamp
                    day_night_status, local_time_str, day_length_str, sunrise_local, sunset_local = get_day_night_and_local_time(
                        current_live_timestamp, # Use live timestamp here
                        weather_data['sys']['sunrise'],
                        weather_data['sys']['sunset'],
                        weather_data['timezone'] # Timezone offset in seconds
                    )
                    
                    # Get weather emoji
                    weather_emoji = get_weather_emoji(main_weather_condition)
                    wind_direction_cardinal = get_wind_direction(wind_deg) if isinstance(wind_deg, (int, float)) else "N/A"

                    # Get innovative weather suggestions
                    weather_suggestions = get_innovative_weather_suggestions(
                        temp, description, wind_speed, humidity, "Daytime" in day_night_status, pressure, visibility
                    )

                    # Main Weather Snapshot - More visual
                    col_main_1, col_main_2 = st.columns([1, 2])
                    with col_main_1:
                        st.markdown(f"<h1 style='font-size: 5em; text-align: center;'>{weather_emoji}</h1>", unsafe_allow_html=True)
                    with col_main_2:
                        st.markdown(f"## {temp}°C")
                        st.markdown(f"*{description.title()}*")
                        st.markdown(f"Feels like: **{feels_like}°C**")
                        st.markdown(f"Local Time: **{local_time_str}** ({day_night_status})")
                            
                    st.markdown("---")

                    # Detailed Metrics & Actionable Advice
                    st.subheader("📊 Key Weather Details:")
                    col_det1, col_det2, col_det3 = st.columns(3)
                    with col_det1:
                        st.metric("Humidity", f"{humidity}%")
                        st.metric("Pressure", f"{pressure} hPa")
                    with col_det2:
                        st.metric("Wind", f"{wind_speed} m/s")
                        st.caption(f"Direction: {wind_direction_cardinal}")
                        st.metric("Cloudiness", f"{cloudiness}%")
                    with col_det3:
                        visibility_km = f"{visibility / 1000:.1f} km" if isinstance(visibility, (int, float)) else visibility
                        st.metric("Visibility", visibility_km)
                        st.markdown(f"**Sunrise:** {sunrise_local}")
                        st.markdown(f"**Sunset:** {sunset_local}")
                        st.caption(f"Day Length: {day_length_str}")
                        
                    st.markdown("---")
                        
                    st.subheader("🚀 Your Quick Guide:")
                    # Display suggestions in a more prominent way, using the new keys
                    for key_icon, value in weather_suggestions.items():
                        st.markdown(f"**{key_icon}:** {value}")
                        
                    # Expander for "What These Numbers Mean"
                    with st.expander("🤔 Understand the Numbers (Tap to learn more)"):
                        st.markdown("""
                        -   **'Feels Like' vs. Actual Temp:** Wind or humidity makes it feel warmer or colder than it truly is.
                        -   **Pressure ($${pressure} hPa$$):** High pressure usually means stable, clear weather. Low pressure often signals approaching storms or changes.
                        -   **Visibility ($${visibility_km}$$):):** How far you can see clearly. Low visibility means fog or heavy rain/snow, affecting driving safety.
                        -   **Cloudiness ($${cloudiness}$$%):):** How much of the sky is covered by clouds. More clouds mean less sun and higher chance of rain.
                        """)
                        
                    # Expander for "Planning Ahead"
                    with st.expander("🗓️ Planning Ahead (Future Tools)"):
                        st.markdown("""
                        -   **Hourly/Daily Forecasts:** Detailed predictions for planning your day/week.
                        -   **Severe Weather Alerts:** Get warnings for storms, floods, etc.
                        -   **UV Index:** Know when to apply sunscreen.
                        -   **Air Quality (AQI):** Pollution levels for health.
                        -   **Pollen/Allergy:** Helpful for allergy sufferers.
                        -   **Stargazing/Photography:** Best times for clear skies or great photos.
                        -   **Health Tips:** Hydration and safety based on weather.
                        """)

                else:
                    st.warning("Could not retrieve weather data for the specified location. Check the error messages above for details.")

        # --- Tab 2: Latest News Section ---
        with tab_news:
            st.header("📰 Latest News")
            with st.spinner(f"Fetching news headlines for {country_to_fetch} (query: '{news_query_to_fetch}' if specified)..."):
                if news_articles:
                    summaries, sentiments = get_news_summary_and_sentiment(news_articles)
                    for i, article in enumerate(news_articles):
                        st.markdown(f"**{i+1}. [{article['title']}]({article['url']})**")
                        if article['author']:
                            st.write(f"   *By: {article['author']}*")
                        if article['description']:
                            st.write(f"   Original: {article['description']}")
                        
                        # Display NLP-generated summary and sentiment
                        st.markdown(f"   **AI Summary:** {summaries[i]}")
                        st.markdown(f"   **AI Sentiment:** {sentiments[i]}")
                        st.write("---")
                    st.caption("*(AI Summaries and Sentiments are simulated for demonstration, using NLP/Transformer models.)*")
                else:
                    st.info(f"No news articles found for '{country_to_fetch}' with query '{news_query_to_fetch}' (if specified), or an error occurred. NewsAPI's 'top-headlines' endpoint primarily provides general country news. Also, remember the free tier has strict rate limits.")

        # --- Tab 3: Real-time Public Transport Status Section ---
        with tab_transport:
            st.header("🚌 Real-time Public Transport Status")
            st.write("Get live updates on key public transport lines in your area.")
            
            if transport_data:
                for line_info in transport_data:
                    status_color = line_info.get("color", "gray") # Default to gray
                    # Use Markdown with inline HTML for colored text and emoji
                    st.markdown(
                        f"**{line_info['line']}**: <span style='color:{status_color}'>**{line_info['status']}**</span> - {line_info['details']}", 
                        unsafe_allow_html=True
                    )
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would connect to real-time public transport APIs.)*")
            else:
                st.info(f"No simulated public transport data available for {city_to_fetch}, {country_to_fetch}. This feature would require integration with local transit APIs.")

        # --- Tab 4: Local Events & Activities Calendar ---
        with tab_events:
            st.header("🗓️ Local Events & Activities Calendar")
            st.write("Discover upcoming events and activities in your selected area.")
            
            if events_data:
                for event in events_data:
                    st.markdown(f"### [{event['title']}]({event['link']})")
                    st.write(f"**Date:** {event['date']} | **Time:** {event['time']}")
                    st.write(f"**Location:** {event['location']}")
                    st.write(f"**Description:** {event['description']}")
                    st.write("---")
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would connect to real-time event APIs.)*")
            else:
                st.info(f"No simulated event data available for {city_to_fetch}, {country_to_fetch}. This feature would require integration with local event APIs.")

        # --- Tab 5: Environmental Health Alerts ---
        with tab_env_health:
            st.header("🌳 Environmental Health Alerts")
            st.write("Important information regarding air quality, pollen levels, and UV index.")
            
            if env_health_data:
                st.subheader("💨 Air Quality Index (AQI)")
                aqi_status_color = "green" if env_health_data['air_quality']['status'] == "Good" else ("orange" if env_health_data['air_quality']['status'] == "Moderate" else "red")
                st.markdown(f"**AQI:** {env_health_data['air_quality']['aqi']} "
                            f"(<span style='color:{aqi_status_color}'>**{env_health_data['air_quality']['status']}**</span>)",
                            unsafe_allow_html=True)
                st.write(f"**Main Pollutants:** {env_health_data['air_quality']['pollutants']}")
                st.info(f"**Advice:** {env_health_data['air_quality']['advice']}")
                st.markdown("---")

                st.subheader("🌼 Pollen Levels")
                pollen_status_color = "green" if env_health_data['pollen']['level'] == "Low" else ("orange" if env_health_data['pollen']['level'] == "Moderate" else "red")
                st.markdown(f"**Level:** <span style='color:{pollen_status_color}'>**{env_health_data['pollen']['level']}**</span>", unsafe_allow_html=True)
                st.write(f"**Type:** {env_health_data['pollen']['type']}")
                st.info(f"**Advice:** {env_health_data['pollen']['advice']}")
                st.markdown("---")

                st.subheader("☀️ UV Index")
                uv_status_color = "green" if env_health_data['uv_index']['status'] == "Low" else ("orange" if env_health_data['uv_index']['status'] == "Moderate" else ("red" if env_health_data['uv_index']['status'] == "High" else "purple"))
                st.markdown(f"**Value:** {env_health_data['uv_index']['value']} "
                            f"(<span style='color:{uv_status_color}'>**{env_health_data['uv_index']['status']}**</span>)",
                            unsafe_allow_html=True)
                st.info(f"**Advice:** {env_health_data['uv_index']['advice']}")
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would connect to real-time environmental health APIs.)*")
            else:
                st.info(f"No simulated environmental health data available for {city_to_fetch}, {country_to_fetch}. This feature would require integration with dedicated APIs.")

        # --- Tab 6: Nearby Malls, Shops, & Services ---
        with tab_nearby_places:
            st.header("🛍️ Nearby Malls, Shops & Services")
            st.write("Find essential businesses and their operating hours in your vicinity.")
            
            if nearby_businesses_data:
                for business in nearby_businesses_data:
                    status_color = "green" if business['status'] == "Open" else "red"
                    st.markdown(f"### [{business['name']}]({business['link']})")
                    st.write(f"**Type:** {business['type']}")
                    st.write(f"**Address:** {business['address']}")
                    st.write(f"**Hours:** {business['hours']} (<span style='color:{status_color}'>**{business['status']}**</span>)", unsafe_allow_html=True)
                    st.write("---")
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would connect to Places APIs for real-time business information.)*")
            else:
                st.info(f"No simulated nearby business data available for {city_to_fetch}, {country_to_fetch}. This feature would require integration with Places APIs.")

        # --- Tab 7: Community Hub ---
        with tab_community:
            st.header("🤝 Community Hub & Resources")
            st.write("Discover local support, educational, and legal aid resources.")
            community_data = get_community_resources(city_to_fetch, country_to_fetch)

            if community_data:
                for resource in community_data:
                    st.markdown(f"### [{resource['name']}]({resource['link']})")
                    st.write(f"**Type:** {resource['type']}")
                    st.write(f"**Details:** {resource['details']}")
                    st.write("---")
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would require integration with local non-profits and government agencies.)*")
            else:
                st.info(f"No simulated community resource data available for {city_to_fetch}, {country_to_fetch}.")

        # --- Tab 8: Sustainability & Environment ---
        with tab_sustainability:
            st.header("♻️ Sustainability & Environment")
            st.write("Find information on local eco-initiatives, waste management, and conservation tips.")
            sustainability_data = get_sustainability_initiatives(city_to_fetch, country_to_fetch)

            if sustainability_data:
                for initiative in sustainability_data:
                    st.markdown(f"### [{initiative['name']}]({initiative['link']})")
                    st.write(f"**Type:** {initiative['type']}")
                    st.write(f"**Details:** {initiative['details']}")
                    st.write("---")
                st.caption("*(Note: This is simulated data for demonstration. A full implementation would require integration with municipal environmental departments and local green organizations.)*")
            else:
                st.info(f"No simulated sustainability data available for {city_to_fetch}, {country_to_fetch}.")


        # --- Tab 9: Intelligent Insights (New ML/NLP/Transformer-based section) ---
        with tab_intelligent_insights:
            st.header("🧠 Intelligent Insights & Predictions")
            st.write("Harnessing the power of AI to provide predictive and personalized insights for your local area.")

            st.subheader("🚗 Predicted Traffic Congestion")
            current_time_for_traffic = datetime.datetime.now().strftime('%I:%M %p')
            current_weather_desc = weather_data['weather'][0]['description'] if weather_data else "unknown"
            
            traffic_prediction = predict_traffic_congestion(city_to_fetch, current_time_for_traffic, current_weather_desc)
            st.markdown(f"**Current Traffic Congestion (Predicted):** {traffic_prediction}")
            st.caption("*(Prediction based on simulated ML model. Real implementation would use live traffic and weather data for more accurate forecasts.)*")
            st.markdown("---")

            st.subheader("🎁 Personalized Local Deals & Recommendations")
            deal_recommendations = get_deal_recommendations(city_to_fetch, current_weather_desc, events_data)
            
            if deal_recommendations:
                for deal in deal_recommendations:
                    st.markdown(f"- {deal}")
                st.caption("*(Recommendations are simulated using a basic logic. A real ML recommendation engine would learn user preferences and analyze market trends.)*")
            else:
                st.info("No personalized deal recommendations at this moment.")
            st.markdown("---")

            st.subheader("🚧 Community Safety Alerts (Conceptual ML)")
            st.markdown("""
            Imagine an AI model analyzing crime reports and social media feeds to provide **proactive safety alerts** for specific neighborhoods.
            -   **Benefit:** Enhanced personal safety and informed decision-making about local areas.
            -   **Requires:** Advanced NLP/ML models (e.g., Transformer networks for anomaly detection) on large, anonymized public safety datasets, with careful ethical considerations.
            """)
            st.markdown("---")
            
            st.subheader("🚶‍♀️ Optimal Commute Mode Advisor (Conceptual ML)")
            st.markdown("""
            An AI-powered advisor could recommend the **best mode of transport** (drive, public transit, cycle, walk) considering live traffic, weather, public transport delays, and your personal preferences (e.g., fastest, cheapest, greenest).
            -   **Benefit:** Saves time, reduces stress, promotes sustainable travel by adapting to dynamic urban conditions.
            -   **Requires:** Complex ML models integrating multiple data streams (traffic, transit APIs, weather, user profiles) and sophisticated route optimization algorithms.
            """)
            st.markdown("---")

            st.subheader("💡 Smart Home Integration for Local IoT Data (Conceptual AI)")
            st.markdown("""
            Imagine connecting your personal smart home devices or public IoT sensors to provide **hyper-personalized environmental insights** (e.g., indoor air quality, specific street-level noise, local micro-climate variations).
            -   **Benefit:** Offers unparalleled granular insights for individual well-being and understanding local micro-environments.
            -   **Requires:** Secure API integrations with smart home platforms (e.g., Google Home, Amazon Alexa), and advanced AI for data fusion and real-time anomaly detection from heterogeneous sensor data.
            """)


        # --- Tab 10: Interactive Map Section ---
        with tab_map:
            st.header("🗺️ Interactive Map")
            st.write("Explore the area around your specified location.")

            # Get approximate coordinates for the city (using a fallback if weather data fails)
            latitude = weather_data['coord']['lat'] if weather_data else -29.8587 # Default to Berea
            longitude = weather_data['coord']['lon'] if weather_data else 31.0218 # Default to Berea

            if latitude != 0 and longitude != 0:
                m = folium.Map(location=[latitude, longitude], zoom_start=12)
                
                # Add a marker for the specified city
                folium.Marker(
                    [latitude, longitude],
                    popup=f"{city_to_fetch}, {country_to_fetch}",
                    tooltip=f"Current Location: {city_to_fetch}"
                ).add_to(m)

                # Display the map
                st.markdown(f'<div style="border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">', unsafe_allow_html=True)
                st.components.v1.html(m._repr_html_(), height=500)
                st.markdown(f'</div>', unsafe_allow_html=True)
                st.caption("Map centered on the specified city. You can pan, zoom, and interact with it.")
            else:
                st.warning("Could not determine precise coordinates for mapping. Map not displayed.")
        
        # --- Tab 11: Conceptual Sections for Advanced Features (Future Ideas) ---
        with tab_future_ideas:
            st.header("💡 More Ideas for the Future")
            st.write("These are additional innovative features that could be integrated:")

            st.markdown("""
            * **Hyper-Local Pollution & Noise Maps:** Visualize real-time air quality and noise hotspots for healthier route planning and leisure.
            * **Green Space & Park Activity Levels:** Real-time occupancy/activity levels in parks and recreational areas.
            * **School & Childcare Alerts:** Timely notifications about school closures, delays, or childcare disruptions.
            * **Health Services & Emergency Facility Locator:** Locate nearby hospitals, clinics, pharmacies, and emergency services.
            * **Local Job Listings & Skill-Matching:** Hyper-local job openings potentially matched to user skills.
            * **Accessibility Information for Public Spaces:** Details on accessible features for public buildings and transport.
            * **Pet-Friendly Locations & Services:** Identifies pet-friendly places and services in the area.
            * **Local Election & Civic Participation Info:** Details on upcoming elections, voter registration, and civic engagement opportunities.
            * **Local Arts & Culture Scene Updates:** A curated feed of exhibitions, performances, and cultural events.
            * **Public Wi-Fi Hotspot Map:** Map showing locations of free public Wi-Fi hotspots.
            * **Volunteer Driver & Companion Services:** Information on services for elderly, disabled, or isolated residents.
            """)
else:
    # Display a placeholder or initial message if location hasn't been detected yet
    st.info("Loading local insights... please wait for auto-detection or enter your location manually in the sidebar.")
    # If geolocation was attempted but failed, indicate manual input is needed
    if st.session_state.initial_location_set and not st.session_state.geolocation_detected:
         st.warning("Automatic location detection failed. Please enter your city and country manually in the sidebar and click 'Get Local Insights!'.")


# --- Footer ---
st.markdown("---")
st.write("Developed by Augustine Khumalo for exploring local real-time data.")
st.write("[Connect with me on LinkedIn](https://www.linkedin.com/in/augustine-khumalo/)")

# --- Auto-refresh mechanism ---
if auto_refresh:
    # This will cause Streamlit to re-run the entire script after a 60-second delay.
    # The time.time() call will then fetch the new current time, updating the display.
    # Cached API calls (weather, news) will only re-fetch if their TTL has expired.
    time.sleep(60)
    st.rerun()
