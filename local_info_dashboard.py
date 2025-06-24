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
OPENWEATHER_REVERSE_GEO_URL = "http://api.openweathermap.org/geo/1.0/reverse" # Still needed if we implement geo-detection later

# --- Initialize session state for inputs (ALL SESSION STATE VARIABLES MUST BE INITIALIZED HERE) ---
if 'city_input' not in st.session_state:
    st.session_state.city_input = "Cape Town"
if 'country_input' not in st.session_state:
    st.session_state.country_input = "South Africa"
if 'news_query_term' not in st.session_state:
    st.session_state.news_query_term = ""
# These flags are now simplified as we are defaulting to Cape Town initially
if 'geolocation_attempted' not in st.session_state:
    st.session_state.geolocation_attempted = True # Assume attempted and settled on default
if 'geolocation_coords' not in st.session_state:
    st.session_state.geolocation_coords = None # Not used for initial load in this version
if 'initial_location_set' not in st.session_state:
    st.session_state.initial_location_set = True # Set to True for automatic initial load
if 'insights_triggered' not in st.session_state:
    st.session_state.insights_triggered = True # Set to True for automatic initial load


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
    This function is kept but not actively used for initial loading in this version.
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
            country = data[0].get('country') # This is ISO code, might need mapping to full name
            return city, country # Return ISO code initially, map later if needed
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
    
    Args:
        query (str): Search query (e.g., city name or topic). Can be empty.
        country_name (str): Full name of the country (e.g., 'South Africa').
        api_key (str): NewsAPI key.
        
    Returns:
        list: List of news articles, or empty list if an error occurs.
    """
    if not api_key or api_key == "YOUR_NEWS_API_KEY":
        st.error("NewsAPI key is not configured. Please set `NEWS_API_KEY`.")
        return []

    # NewsAPI expects 2-letter ISO country codes.
    country_codes = {
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
    
    iso_country_code = country_codes.get(country_name.title(), None) # Convert input to title case for lookup

    if not iso_country_code:
        st.warning(f"Could not determine 2-letter country code for '{country_name}'. NewsAPI 'top-headlines' endpoint requires a valid country code. Attempting to fetch with country code 'us' as a fallback, but results may not be relevant.")
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

# --- Public Transport Status Helper Function ---
def get_public_transport_status(city: str, country: str):
    """
    Simulates fetching real-time public transport status for a given city and country.
    In a real application, this would integrate with specific public transport APIs
    (e.g., city transit authority APIs, GTFS-Realtime feeds).
    
    Returns a list of dictionaries, each representing a public transport line's status.
    """
    if city.lower() == "cape town" and country.lower() == "south africa":
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

    if city.lower() == "cape town" and country.lower() == "south africa":
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


# --- End of Helper Functions ---


# --- 1. Dashboard Configuration and Title ---
st.set_page_config(
    page_title=PAGE_TITLE,
    layout=LAYOUT,
    initial_sidebar_state=INITIAL_SIDEBAR_STATE
)

st.title("📍 Local Insights Dashboard")
st.markdown("---")

# --- Introduction and User Guide ---
st.info(
    """
    **Welcome!** Get instant local weather, top news, and an interactive map.

    **How to use:**
    1.  Insights for **Cape Town, South Africa** load automatically.
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
st.session_state.city_input = st.sidebar.text_input("City:", value=st.session_state.city_input, help="E.g., London, New York", key="sidebar_city_input")
st.session_state.country_input = st.sidebar.text_input("Country:", value=st.session_state.country_input, help="E.g., United States, France", key="sidebar_country_input")

st.sidebar.markdown("---")
st.sidebar.write("Optional: Filter news headlines.")
st.session_state.news_query_term = st.sidebar.text_input("News Search Term (Optional):", value=st.session_state.news_query_term, help="e.g., 'local politics', 'sports', 'economy'. Leave empty for general headlines.", key="sidebar_news_query")

# Button to trigger data fetch (explicitly set insights_triggered)
if st.sidebar.button("Get Local Insights! 🔄"):
    st.session_state.insights_triggered = True
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
if st.session_state.insights_triggered:
    city_to_fetch = st.session_state.city_input
    country_to_fetch = st.session_state.country_input
    news_query_to_fetch = st.session_state.news_query_term

    if not city_to_fetch or not country_to_fetch:
        st.warning("Please enter both a City and a Country to get insights.")
    else:
        if NEWS_API_KEY == "YOUR_NEWS_API_KEY" or OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
            st.error("API keys are not configured. Please update `NEWS_API_KEY` and `OPENWEATHER_API_KEY` in the code.")
        else:
            st.subheader(f"Insights for {city_to_fetch}, {country_to_fetch}")
            
            # Create tabs for different sections
            tab_weather, tab_news, tab_transport, tab_events, tab_map, tab_future_ideas = st.tabs([
                "☀️ Weather", "📰 News", "🚌 Transport", "🗓️ Events", "🗺️ Map", "💡 Future Ideas"
            ])

            # --- Tab 1: Weather Section ---
            with tab_weather:
                st.header("☀️ Current Weather Snapshot")
                with st.spinner(f"Fetching weather data for {city_to_fetch}..."):
                    weather_data = get_weather(city_to_fetch, country_to_fetch, OPENWEATHER_API_KEY)
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
                # Removed st.markdown("---") as tabs implicitly handle separation

            # --- Tab 2: Latest News Section ---
            with tab_news:
                st.header("📰 Latest News")
                with st.spinner(f"Fetching news headlines for {country_to_fetch} (query: '{news_query_to_fetch}' if specified)..."):
                    news_articles = get_news(news_query_to_fetch, country_to_fetch, NEWS_API_KEY)
                    if news_articles:
                        for i, article in enumerate(news_articles):
                            st.write(f"**{i+1}. [{article['title']}]({article['url']})**")
                            if article['author']:
                                st.write(f"   *By: {article['author']}*")
                            if article['description']:
                                st.write(f"   {article['description']}")
                            st.write("---")
                    else:
                        st.info(f"No news articles found for '{country_to_fetch}' with query '{news_query_to_fetch}' (if specified), or an error occurred. NewsAPI's 'top-headlines' endpoint primarily provides general country news. Try leaving the 'News Search Term' empty for broader headlines or ensuring your country is properly mapped (full country name like 'South Africa'). Also, remember the free tier has strict rate limits.")
                # Removed st.markdown("---")

            # --- Tab 3: Real-time Public Transport Status Section ---
            with tab_transport:
                st.header("🚌 Real-time Public Transport Status")
                st.write("Get live updates on key public transport lines in your area.")
                transport_data = get_public_transport_status(city_to_fetch, country_to_fetch)

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
                # Removed st.markdown("---")

            # --- Tab 4: Local Events & Activities Calendar ---
            with tab_events:
                st.header("🗓️ Local Events & Activities Calendar")
                st.write("Discover upcoming events and activities in your selected area.")
                events_data = get_local_events(city_to_fetch, country_to_fetch)

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
                # Removed st.markdown("---")

            # --- Tab 5: Interactive Map Section ---
            with tab_map:
                st.header("🗺️ Interactive Map")
                st.write("Explore the area around your specified location.")

                # Get approximate coordinates for the city (using a fallback if weather data fails)
                latitude = weather_data['coord']['lat'] if weather_data else 0
                longitude = weather_data['coord']['lon'] if weather_data else 0

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
                # Removed st.markdown("---")
            
            # --- Tab 6: Conceptual Sections for Advanced Features (Future Ideas) ---
            with tab_future_ideas:
                st.header("💡 Future Enhancements (Conceptual)")
                st.write("Here are some innovative ideas for future features that could be added to this dashboard:")

                st.subheader("🚧 Real-time Traffic & Accidents")
                st.markdown("""
                Get **live traffic updates** and **accident reports**.
                -   **Benefit:** Plan routes, avoid delays, enhance safety.
                -   **Requires:** Paid Traffic/Mapping APIs (e.g., Google Maps Platform, HERE).
                """)
                st.markdown("---")

                st.subheader("🛍️ Nearby Malls, Shops, & Services (with Hours)")
                st.markdown("""
                Find **nearby businesses** (malls, shops, garages) and their **closing hours**.
                -   **Benefit:** Easily locate services and know if they're open.
                -   **Requires:** Paid Places APIs (e.g., Google Places, Foursquare). Real-time hours are often complex.
                """)
                st.markdown("---")

                st.subheader("🩺 Environmental Health Alerts (Air Quality, Pollen, UV Index)")
                st.markdown("""
                Receive **critical health-related environmental data**.
                -   **Benefit:** Helps sensitive individuals plan outdoor activities, protect skin, and manage allergies.
                -   **Requires:** Dedicated Air Quality, Pollen, and UV Index APIs (e.g., IQAir, BreezoMeter, AccuWeather).
                """)
                st.markdown("---")

                st.subheader("🚨 Local Resource Availability & Public Service Announcements")
                st.markdown("""
                Stay informed about **local utility schedules (e.g., load shedding, water supply)** and **important public announcements**.
                -   **Benefit:** Enables proactive planning for potential disruptions and keeps the community informed.
                -   **Requires:** Integration with municipal data feeds, utility company APIs, or local government communication channels.
                """)
                st.markdown("---")

                st.subheader("🔇 Hyper-Local Pollution & Noise Maps")
                st.markdown("""
                Visualize **real-time air pollution levels and noise hotspots** in specific neighborhoods.
                -   **Benefit:** Allows users to choose healthier routes for walks/runs, find quiet areas for relaxation, or identify areas to avoid due to noise/pollution.
                -   **Requires:** Environmental sensor networks, urban data platforms, and advanced mapping capabilities to overlay real-time data.
                """)
                st.markdown("---")

                st.subheader("🚔 Community Safety & Crime Hotspots")
                st.markdown("""
                Access **anonymized, aggregated data on recent crime incidents or safety alerts** in local areas.
                -   **Benefit:** Enhances personal safety awareness, helps in choosing safer routes or neighborhoods, and promotes community vigilance.
                -   **Requires:** Partnership with local law enforcement agencies, public crime data feeds, and careful aggregation/anonymization to ensure privacy.
                """)
                st.markdown("---")

                st.subheader("🚶‍♀️ Optimal Commute Mode Advisor")
                st.markdown("""
                Get **personalized recommendations for the best mode of transport** (driving, public transit, cycling, walking) based on live traffic, weather, public transport delays, and user preferences.
                -   **Benefit:** Saves time, reduces stress, promotes sustainable travel, and adapts to dynamic urban conditions.
                -   **Requires:** Comprehensive traffic APIs, real-time public transit data, weather data, and route optimization algorithms.
                """)
                st.markdown("---")

                st.subheader("💸 Personalized Local Deals & Promotions")
                st.markdown("""
                Receive **tailored recommendations for discounts, promotions, and special offers** from local businesses (restaurants, shops, services).
                -   **Benefit:** Helps users save money, discover local businesses, and enhances their shopping/dining experiences.
                -   **Requires:** Partnership with local businesses, deal aggregation platforms, and potentially user preference profiling for personalization.
                """)
                st.markdown("---")

                st.subheader("🍎 Local Food Access & Community Resources")
                st.markdown("""
                Information on **nearby food banks, community pantries, farmers' markets, and healthy food initiatives**.
                -   **Benefit:** Helps address food insecurity, promotes local food systems, and connects residents with vital resources.
                -   **Requires:** Data from local non-profits, municipal health departments, and food cooperative listings.
                """)
                st.markdown("---")

                st.subheader("🏞️ Green Space & Park Activity Levels")
                st.markdown("""
                Displays **real-time occupancy or activity levels in local parks, beaches, or recreational areas**.
                -   **Benefit:** Helps users find less crowded spaces for relaxation or exercise, especially during peak times.
                -   **Requires:** IoT sensors (e.g., foot traffic counters, Wi-Fi analytics), anonymized mobile data, or community reporting.
                """)
                st.markdown("---")

                st.subheader("🤝 Community Volunteering & Engagement Opportunities")
                st.markdown("""
                A curated feed of **local volunteering opportunities, community clean-up drives, and civic engagement events**.
                -   **Benefit:** Fosters community spirit, allows residents to contribute to local causes, and provides avenues for social connection.
                -   **Requires:** Partnerships with local charities, non-profits, and community organizations.
                """)
                st.markdown("---")

                st.subheader("🏫 School & Childcare Alerts")
                st.markdown("""
                Provides **timely notifications about school closures, delayed openings, or childcare facility disruptions** due to weather, health, or other emergencies.
                -   **Benefit:** Crucial for parents and guardians to plan their day and ensure child safety.
                -   **Requires:** Integration with school district alert systems, local education authority feeds, or verified public announcements.
                """)
                st.markdown("---")

                st.subheader("⚡ Local Energy Consumption & Efficiency Tips")
                st.markdown("""
                Offers insights into **local energy grid status (if available) and personalized tips for energy saving** based on real-time weather and energy prices.
                -   **Benefit:** Empowers users to reduce their carbon footprint, save on utility bills, and understand local energy demand.
                -   **Requires:** Data from local utility providers (where available), smart meter integrations, and energy efficiency algorithms.
                """)
                st.markdown("---")

                st.subheader("♻️ Waste Collection Schedules & Recycling Guidance")
                st.markdown("""
                Provides **personalized waste collection schedules (trash, recycling, green waste)** and clear guidance on what can be recycled and where.
                -   **Benefit:** Helps residents manage waste effectively, improve recycling rates, and avoid missed collections.
                -   **Requires:** Municipal waste management data feeds, localized recycling guidelines, and notification systems.
                """)
                st.markdown("---")

                st.subheader("💉 Health Services & Emergency Facility Locator")
                st.markdown("""
                Locate **nearby hospitals, clinics, pharmacies, and emergency services** with real-time waiting times or operational status if available.
                -   **Benefit:** Crucial for quick access to healthcare in emergencies or for routine medical needs.
                -   **Requires:** Integration with health service directories, hospital APIs, and emergency service databases.
                """)
                st.markdown("---")

                st.subheader("👷 Local Job Listings & Skill-Matching")
                st.markdown("""
                Displays **hyper-local job openings** and can potentially match them to user-provided skills or preferences.
                -   **Benefit:** Connects residents with employment opportunities close to home, fostering local economic growth.
                -   **Requires:** Integration with local job boards, employment agencies, and skill-matching algorithms.
                """)
                st.markdown("---")

                st.subheader("💧 Water Quality & Conservation Tips")
                st.markdown("""
                Provides **updates on local water quality, significant water incidents (e.g., boil water advisories), and personalized water-saving tips**.
                -   **Benefit:** Ensures public health related to water, promotes responsible water usage, and informs about potential issues.
                -   **Requires:** Data from local water utilities, environmental agencies, and water conservation guidance.
                """)
                st.markdown("---")

                st.subheader("♿ Accessibility Information for Public Spaces")
                st.markdown("""
                Information on **accessibility features (e.g., ramps, accessible restrooms, tactile paving)** for public buildings, parks, and transport hubs.
                -   **Benefit:** Improves navigation and inclusion for individuals with disabilities, parents with strollers, or anyone with mobility challenges.
                -   **Requires:** Crowdsourced data, municipal accessibility audits, and detailed building information.
                """)
                st.markdown("---")

                st.subheader("🌿 Urban Farming & Community Garden Resources")
                st.markdown("""
                Information on **local community gardens, urban farming initiatives, workshops, and resources for growing food**.
                -   **Benefit:** Promotes sustainable living, food security, community building, and access to fresh produce.
                -   **Requires:** Data from local agricultural programs, community organizations, and gardening associations.
                """)
                st.markdown("---")

                st.subheader("🐾 Pet-Friendly Locations & Services")
                st.markdown("""
                Identifies **pet-friendly parks, restaurants, shops, veterinarians, and animal shelters** in the area.
                -   **Benefit:** Helps pet owners find suitable places and services for their companions, enhancing the quality of life for pets and their owners.
                -   **Requires:** Aggregated data from business listings, local pet organizations, and community reviews.
                """)
                st.markdown("---")

                st.subheader("💡 Smart Home Integration & Local IoT Data")
                st.markdown("""
                (Conceptual) Connects to personal smart home devices or public IoT sensors for **hyper-personalized environmental data** (e.g., indoor air quality, specific street-level noise).
                -   **Benefit:** Offers unparalleled granular insights for individual well-being and local micro-environments.
                -   **Requires:** Secure API integrations with smart home platforms (e.g., Google Home, Amazon Alexa), and access to local public IoT networks.
                """)
                st.markdown("---")

                st.subheader("🗳️ Local Election & Civic Participation Info")
                st.markdown("""
                Provides **details on upcoming local elections (polling stations, candidate info), voter registration, and opportunities for civic engagement**.
                -   **Benefit:** Encourages informed participation in local governance and strengthens democratic processes.
                -   **Requires:** Data from election commissions, municipal civic engagement offices, and non-partisan voter information organizations.
                """)
                st.markdown("---")

                st.subheader("🎨 Local Arts & Culture Scene Updates")
                st.markdown("""
                A curated feed of **exhibitions, live performances, workshops, and cultural events** from local galleries, theaters, and community centers.
                -   **Benefit:** Promotes local culture, helps residents discover artistic experiences, and supports local artists.
                -   **Requires:** Partnerships with local arts councils, cultural institutions, and event listing platforms.
                """)
                st.markdown("---")

                st.subheader("📚 Library & Community Center Schedules")
                st.markdown("""
                Information on **opening hours, events, workshops, and available services** at local libraries and community centers.
                -   **Benefit:** Connects residents with free educational resources, recreational activities, and community support.
                -   **Requires:** Data from local library systems and community center directories.
                """)
                st.markdown("---")

                st.subheader("🧑‍⚖️ Local Legal Aid & Public Advocacy Resources")
                st.markdown("""
                Provides information on **free or low-cost legal aid clinics, public advocacy groups, and community justice initiatives**.
                -   **Benefit:** Helps vulnerable residents access legal assistance and empowers them to address local issues.
                -   **Requires:** Data from legal aid societies, non-profit organizations, and local government legal services.
                """)
                st.markdown("---")

                st.subheader("📶 Public Wi-Fi Hotspot Map")
                st.markdown("""
                A map showing **locations of free public Wi-Fi hotspots** in the city.
                -   **Benefit:** Essential for residents and visitors to stay connected, especially those with limited data access.
                -   **Requires:** Data from municipal public Wi-Fi initiatives, community-contributed lists, or partnership with telecom providers.
                """)
                st.markdown("---")

                st.subheader("🌲 Local Reforestation & Green Initiative Tracking")
                st.markdown("""
                Information on **local tree-planting campaigns, urban greening projects, and progress towards environmental goals**.
                -   **Benefit:** Engages residents in environmental stewardship and provides transparency on local sustainability efforts.
                -   **Requires:** Data from municipal environmental departments, non-profit conservation groups, and ecological surveys.
                """)
                st.markdown("---")

                st.subheader("🛒 Local Product Sourcing & 'Buy Local' Guide")
                st.markdown("""
                A directory or map of **local businesses offering unique, locally sourced products** (e.g., crafts, produce, artisanal goods).
                -   **Benefit:** Supports local economy, promotes sustainable consumption, and helps users find unique items.
                -   **Requires:** Curated business directories, local chamber of commerce data, and community submissions.
                """)
                st.markdown("---")

                st.subheader("♿ Volunteer Driver & Companion Services")
                st.markdown("""
                Information on **local volunteer services offering transport or companionship** for elderly, disabled, or isolated residents.
                -   **Benefit:** Enhances mobility and social inclusion for vulnerable populations, connecting them with community support.
                -   **Requires:** Partnerships with senior centers, disability organizations, and volunteer networks.
                """)
                st.markdown("---")


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
