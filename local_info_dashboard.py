# This Streamlit application provides real-time local insights
# including weather, news, and an interactive map for a specified location.

import streamlit as st
import requests
import pandas as pd
import folium # For interactive maps
from folium.plugins import MarkerCluster # For clustering markers on the map
import json # To parse JSON responses sometimes needed
import datetime # For handling timestamps for day/night calculation
# import pytz # While pytz offers named timezones, OpenWeatherMap provides offset,
#              # datetime.timezone handles offset directly without extra install.

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
# OpenWeatherMap Geocoding API is usually implied by 'q' parameter in current weather,
# but a dedicated geocoding call could be used for more robust coordinate lookup.


# --- 1. Dashboard Configuration and Title ---
st.set_page_config(
    page_title=PAGE_TITLE,
    layout=LAYOUT,
    initial_sidebar_state=INITIAL_SIDEBAR_STATE
)

st.title("📍 Local Insights Dashboard")
st.markdown("---")

# --- Introduction and User Guide (Simplified) ---
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

# --- Initialize session state for inputs ---
if 'city_input' not in st.session_state:
    st.session_state.city_input = "Cape Town"
if 'country_input' not in st.session_state:
    st.session_state.country_input = "South Africa"
if 'news_query_term' not in st.session_state:
    st.session_state.news_query_term = ""
if 'insights_triggered' not in st.session_state: # New state to manage initial load vs button click
    st.session_state.insights_triggered = True # Set to True for automatic initial load


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
if st.sidebar.button("Get Local Insights!"):
    st.session_state.insights_triggered = True
    # Clear cache when explicitly fetching new insights
    st.cache_data.clear()


# These warnings are crucial for API key setup
if not NEWS_API_KEY or NEWS_API_KEY == "YOUR_NEWS_API_KEY":
    st.sidebar.warning("Please replace 'YOUR_NEWS_API_KEY' in the code with your actual NewsAPI key.")
if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
    st.sidebar.warning("Please replace 'YOUR_OPENWEATHER_API_KEY' in the code with your actual OpenWeatherMap API key.")


# --- 3. Data Fetching Functions ---

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

# Helper function to determine day/night and local time
def get_day_night_and_local_time(current_timestamp, sunrise_timestamp, sunset_timestamp, timezone_offset_seconds):
    tz_delta = datetime.timedelta(seconds=timezone_offset_seconds)
    tz_info = datetime.timezone(tz_delta)

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

# Helper function to get wind direction from degrees
def get_wind_direction(deg):
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / (360. / len(directions)))
    return directions[idx % len(directions)]

# Helper function to get a weather emoji
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

# Helper function for innovative weather suggestions (More concise and direct)
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
        suggestions["❤️ Health Tip"] = "Stay hydrated, even when cool. Dress appropriately."
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


# --- 4. Main Content Display ---

# This block will now run automatically on page load or when the button is clicked
# Check if insights should be triggered (initial load or button click)
if st.session_state.insights_triggered: # Always display if triggered
    # Use st.session_state values directly
    city_to_fetch = st.session_state.city_input
    country_to_fetch = st.session_state.country_input
    news_query_to_fetch = st.session_state.news_query_term

    if not city_to_fetch or not country_to_fetch:
        st.warning("Please enter both a City and a Country to get insights.")
    else:
        # Check if API keys are still placeholders before proceeding with API calls
        if NEWS_API_KEY == "YOUR_NEWS_API_KEY" or OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
            st.error("API keys are not configured. Please update `NEWS_API_KEY` and `OPENWEATHER_API_KEY` in the code.")
        else:
            st.subheader(f"Insights for {city_to_fetch}, {country_to_fetch}")
            
            # --- Weather Section ---
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
                    
                    # Get day/night indicator and local time
                    day_night_status, local_time_str, day_length_str, sunrise_local, sunset_local = get_day_night_and_local_time(
                        weather_data['dt'],
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
                        -   **Visibility ($${visibility_km}$$):** How far you can see clearly. Low visibility means fog or heavy rain/snow, affecting driving safety.
                        -   **Cloudiness ($${cloudiness}$$%):** How much of the sky is covered by clouds. More clouds mean less sun and higher chance of rain.
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
            st.markdown("---")

            # --- Latest News Section ---
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
            st.markdown("---")

            # --- Interactive Map Section ---
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
            st.markdown("---")
            
            # --- Conceptual Sections for Advanced Features (General) ---
            st.header("💡 More Future Enhancements (Conceptual)")

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


# --- Footer ---
st.markdown("---")
st.write("Developed by Augustine Khumalo for exploring local real-time data.")
st.write("[Connect with me on LinkedIn](https://www.linkedin.com/in/augustine-khumalo/)")
