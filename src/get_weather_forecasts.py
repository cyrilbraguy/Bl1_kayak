# ====================================================================
# Kayak project Cyril 
# module 3 : 
# get_weather_forecasts.py 
# (c) 2026-09-20 
# ====================================================================
# get weather forecasts of all cities by calling the api 

# determine the top 7 cities with the best weather conditions for next 5 days
#  daily.pop and daily.rain : expected volume of rain in next days 
# temperature + humidity 

# API call 2.5 soon deprecated:
#https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude={part}&appid={API key}


#WEATHER_API_KEY = weather_api_key
from __future__ import annotations
import logging
import pandas as pd
import requests
from datetime import datetime, date
from typing import Callable, Iterable, NamedTuple

logger = logging.getLogger(__name__)

from config_kayak import (
    WEATHER_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_REGION,
    POIDS_CONFORT, TEMP_OPTIMALE, TEMP_TOLERANCE, VENT_MAX,

    BASE_URL_NOMINATIM, BASE_URL_OPENWEATHERMAP,
    CONFIG_CITIES_FILE ,
    MAX_CITIES_NUMBER,
    DATA_DIR,
    DATA_DIR_CONFIG, 
    DATA_DIR_CSV,
    DATA_DIR_HTML, 
    DATA_DIR_JSON, DATA_DIR_JSON_CITIES, DATA_DIR_JSON_HOTELS, 
    VALID_TYPES,  USER_AGENT,
    HEADERS, DEFAULT_PARAMS
    
)

def comfort_score(summary: pd.DataFrame, poids: dict = POIDS_CONFORT,
                  t_opt: float = TEMP_OPTIMALE) -> pd.Series:
    """Score de confort météo entre 0 et 1 (1 = idéal)."""
    if abs(sum(poids.values()) - 1) > 1e-9:
        raise ValueError(f"Les poids doivent sommer à 1 (somme = {sum(poids.values()):.2f})")
    composantes = {
        "ciel":        summary["clear_sky_ratio"],
        "humidite":    1 - summary["humidity_mean"] / 100,
        "pluie":       1 - summary["pop_max"],
        "temperature": 1 - (summary["temp_mean"] - t_opt).abs() / TEMP_TOLERANCE,
        "vent":        1 - summary["wind_speed_max"] / VENT_MAX,
    }
    score = sum(poids[k] * composantes[k].clip(0, 1) for k in poids)
    return score.clip(0, 1).round(2)


def get_weather(lat:float, lon:float) -> dict :
    """ get weatherforecast from openweathermap
    """
    params = {
        "lat": lat, "lon": lon,
        #"cnt": 100,
        "units": "metric",
        "appid": WEATHER_API_KEY,
    }
    response = requests.get(url=f"{BASE_URL_OPENWEATHERMAP}/forecast" ,
                            params = params,
                            timeout = 10)
    if response.status_code == 200:
        return response.json()
    print(f"  openweathermap error {response.status_code}: {response.text[:200]}")
    return None

def compile_weather(weather_data)-> pd.DataFrame:
    """ compile in a dataFrame weather data 
    coming from call weather_api
    that is in json format"""

    df_weather = pd.json_normalize(
        weather_data["list"],
        sep="_",
        record_path=["weather"],      # extrait weather (liste imbriquée) comme colonnes séparées
        meta=[
            "dt", "dt_txt", "visibility", "pop",
            ["main", "temp"], ["main", "feels_like"], ["main", "temp_min"], ["main", "temp_max"],
            ["main", "pressure"], ["main", "humidity"], ["main", "dew_point"],
            ["wind", "speed"], ["wind", "deg"], ["wind", "gust"],
            ["clouds", "all"], ["sys", "pod"],
        ],
        meta_prefix="",
        errors="ignore",              # tolère les champs absents (ex: pas de gust sur certaines entrées)
        record_prefix="weather_",
    )

    df_weather["datetime"] = pd.to_datetime(df_weather["dt_txt"])
    df_weather = df_weather.sort_values("datetime").reset_index(drop=True)
    return df_weather


def compile_weather2(data):
    """ compile in a dataFrame weather data 
        coming from call weather_api
        that is in json format"""
    df = pd.json_normalize(data["list"], sep="_")
    # df["weather_main"] = df["weather"].apply(lambda w: w[0]["main"] if w else None)
    # df["weather_description"] = df["weather"].apply(lambda w: w[0]["description"] if w else None)
    # df = df.drop(columns="weather")
    
    # 2eme iter : 
    # Extraction du champ weather (liste imbriquée avec 1 élément par entrée)
    weather_df = pd.json_normalize(df["weather"].apply(lambda w: w[0] if w else {}))
    weather_df = weather_df.add_prefix("weather_")

    df = pd.concat([df.drop(columns="weather"), weather_df], axis=1)
    df["datetime"] = pd.to_datetime(df["dt_txt"])
    df = df.sort_values("datetime").reset_index(drop=True)

        
    return df

def summarize_weather(df: pd.DataFrame, hour_start: int = 8, hour_end: int = 20) -> pd.DataFrame:
    """ summarize weather on 5 days forecast
        compute daily rain and daily pop (probability of precipitation) between hour_start and hour_end
        compute daily mean temperature and humidity
        comfort_score : 0 to 1, based on several criteria (clear sky, temp, humidity, rain, wind)
        

    Args:
        df (pd.DataFrame): [description]
        hour_start (int, optional): [description]. Defaults to 8.
        hour_end (int, optional): [description]. Defaults to 20.

    Returns:
        pd.DataFrame: dataframe with summary of weather for each day, with columns : 
        date, rain_sum, pop_max, temp_mean, humidity_mean, clear_slots_count, 
        rain_slots_count, wind_speed_max, n_slots, clear_sky_ratio, rain_ratio, is_pleasant_day, 
        comfort_score : 
    """
    # define criteria 
    # compute summary on several criteria 
    # determine the top 7 cities with the best weather conditions for next 7 days
    #  daily.pop and daily.rain : expected volume of rain in next days 
    # temperature + humidity 
    
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour

    mask = (df["hour"] >= hour_start) & (df["hour"] <= hour_end)
    day_df = df.loc[mask].copy()

    if "rain_3h" not in day_df.columns:
        day_df["rain_3h"] = 0
    if "pop" not in day_df.columns:
        day_df["pop"] = 0
        
    day_df['is_clear'] = day_df['weather_main'].isin(['Clear']) 
    day_df['is_rain'] = day_df['weather_main'].isin(['Rain', 'Drizzle', 'Thunderstorm'])
    day_df['main_temp'] = day_df['main_temp'].fillna(0)
    day_df['main_humidity'] = day_df['main_humidity'].fillna(0)
    day_df["rain_3h"] = day_df["rain_3h"].fillna(0)
    day_df["pop"] = day_df["pop"].fillna(0)
    day_df["wind_speed"] = day_df["wind_speed"].fillna(0)

    summary = day_df.groupby("date").agg(
        rain_sum=("rain_3h", "sum"),
        pop_max=("pop", "max"),
        temp_mean=("main_temp", "mean"),
        humidity_mean=("main_humidity", "mean"),
        clear_slots_count=("is_clear", "sum"),
        rain_slots_count=("is_rain", "sum"),
        wind_speed_max=("wind_speed", "max"),
        n_slots=("hour", "count"),
    ).reset_index()

    summary["clear_sky_ratio"] = summary["clear_slots_count"] / summary["n_slots"]
    summary["rain_ratio"] = summary["rain_slots_count"] / summary["n_slots"]


    # Critère booléen "jour agréable"
    summary["is_pleasant_day"] = (
        (summary["clear_sky_ratio"] >= 0.5)
        & summary["temp_mean"].between(15, 27)
        & (summary["humidity_mean"] < 70)
        & (summary["rain_sum"] < 0.5)
        & (summary["rain_slots_count"] == 0)
        & (summary["pop_max"] < 0.3)
        & (summary["wind_speed_max"] < 11)  # m/s ≈ 40 km/h
    )

    # Bonus : score continu (0 à 1) plutôt que binaire, plus nuancé
    # We call a dedicated function that can be parametered:
    summary["comfort_score"] = comfort_score(summary)

    # summary["comfort_score"] = (
    #     0.30 * summary["clear_sky_ratio"]
    #     + 0.25 * (1 - (summary["humidity_mean"] / 100)).clip(0, 1)
    #     + 0.20 * (1 - summary["pop_max"]).clip(0, 1)
    #     + 0.15 * (1 - (summary["temp_mean"] - 21).abs() / 15).clip(0, 1)  # optimum ~21°C
    #     + 0.10 * (1 - (summary["wind_speed_max"] / 15)).clip(0, 1)
    # ).clip(0, 1).round(2)

    return summary


def get_weather_data_for_cities(df_cities: pd.DataFrame, scraped_dt : pd.Timestamp) -> pd.DataFrame:
    """ collect weather data for all cities from a df_cities dataftrame 
        - get weather forecasts from openweathermap API for each city (lat, lon)
        - compile the weather data in a dataframe from json format
        - summarize the weather data on several criteria on a daily base 
            (comfort_score, clear_sky_ratio, rain_ratio, is_pleasant_day)
        - return a dataframe with summary of weather for each city and each date

    Args:
        df_cities (pd.DataFrame): pd.DataFrame of cities 
                                  coming from for example get_coordinates_cities(cities_list_df)
                                  with  columns at least :
                                  city_name, city_lat, city_lon of all cities  
        scraped_dt (pd.Timestamp): timestamp of scraping activity to uniformize scraped datetime on all tables

    Returns:
        pd.DataFrame: DataFrame of weather forecast
    """
    if not scraped_dt:
            scraped_dt = pd.Timestamp.now()
            
    results_weather = []
    for _, row in df_cities.iterrows():
        name = row['city_name']
        lat, lon = row['city_lat'], row['city_lon']
        
        # print(f"{name}\n")
        weather_forecast = get_weather(lat, lon)
        df_weather = compile_weather2(weather_forecast)
        
        sw = summarize_weather(df_weather)
        sw['city'] = name
        sw['scraped_at'] = scraped_dt
        results_weather.append(sw)
        
        # display(sw)  # Optionally display the summary for each city
    
    return pd.concat(results_weather, ignore_index=True)

class SearchKey(NamedTuple): # to define later 
    checkin: date
    checkout: date
    

def run_weather_searches(
    df_weather_summary: pd.DataFrame,
    windows: list[tuple[date, date]],
    select_weather_cities_fn: Callable,
    scraped_dt: pd.Timestamp,
    top_n: int = 7, 
     
    ) -> pd.DataFrame: # tuple[pd.DataFrame, list[SearchKey]]
    """search for cities with best weather conditions for each window of dates

    Args:
        df_weather_summary (pd.DataFrame):  weather forecasts coming from get_weather_data_for_cities()
                                            and columns : comfort_score, clear_sky_ratio, rain_ratio, is_pleasant_day
                                            and in addition 'scraped_at': timestamp of weather scrap
                                            
        windows (list[tuple[date, date]]):  time windows for which we want to select best cities 
                                            coming from build_date_windows(result_weather["date"].unique())
                                            
        select_weather_cities_fn (Callable): function to select best cities based on weather criteria, 
                                             e.g. select_best_weather_cities
                                             
        scraped_dt (pd.Timestamp):  timestamp of scrapped data to uniformize scraped datetime on all tables
        
        top_n (int, optional):      number of cities to select. Defaults to 7.

    Returns:
        pd.DataFrame: result of selection of best cities for each window, with weather summary
                      with columns : city, checkin_date, checkout_date, avg_comfort_score, rain_sum, temp, humidity, clear_slots, rain_slots, wind_speed_max, scraped_at
    """
    #skip_keys = skip_keys or set()
    weather_summary_windows: list[pd.DataFrame] = []
    failed: list[SearchKey] = []
    
    for checkin, checkout in windows:
        print(f"select best weather cities for window {checkin} - {checkout}")
        
        try:
            weather_sum_win = select_weather_cities_fn(
                                    df_weather_summary, 
                                    top_n = top_n, 
                                    start_date= checkin, end_date= checkout)
            weather_sum_win["scraped_at"] = scraped_dt   
        except Exception:
            logger.exception("Échec de la weather best cities selection %s", (checkin, checkout))
            #failed.append(key)
            continue 
        
        if weather_sum_win is None or weather_sum_win.empty:
            logger.warning("Aucune meteo pour %s", (checkin, checkout))
            continue

        weather_sum_win = weather_sum_win.copy()
        weather_sum_win["checkin_date"] = checkin
        weather_sum_win["checkout_date"] = checkout
        
        weather_summary_windows.append(weather_sum_win)
        
    result_weather_windows = pd.concat(weather_summary_windows, ignore_index=True) if weather_summary_windows else pd.DataFrame() 
    return result_weather_windows #, failed

      
def select_best_weather_cities(df_weather_summary: pd.DataFrame, top_n: int = 7, 
                               start_date: str | pd.Timestamp | None = None , 
                               end_date: str | pd.Timestamp | None = None
                               ) -> pd.DataFrame:
    """Select the top N cities with the best weather conditions based on comfort_score.
    between optional dates 
    Args:
        df_weather_summary (pd.DataFrame):  complete weather summary dataframe with columns : 
                                            city, date, comfort_score, clear_sky_ratio, rain_ratio, is_pleasant_day, 
                                            scraped_at
                                            coming from get_weather_data_for_cities()
                                            
        top_n (int, optional): number of cities to select. Defaults to 7.
        start_date (str, optional): start date for the weather forecast. Defaults to None will take beginning of data.
        end_date (str, optional): end date for the weather forecast. Defaults to None will take end of data

    Raises:
        ValueError: [description]

    Returns:
        pd.DataFrame: listint cities with summary weather conditions for the given date window, with columns :
                      city, checkin_date, checkout_date, avg_comfort_score, rain_sum, temp
                        , humidity, clear_slots, rain_slots, wind_speed_max, scraped_at
    """
        

    # Group by city and calculate the average comfort score over the forecast period
    df_weather_summary["date"] = pd.to_datetime(df_weather_summary["date"])
    date_span = df_weather_summary["date"].unique()
    min_date = date_span.min()  # today !! 
    max_date = date_span.max() # last day !!
    
    start_date = pd.Timestamp(start_date) if start_date else min_date 
    end_date = pd.Timestamp(end_date) if end_date else max_date

    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) postérieure à end_date ({end_date})")
        
    mask = df_weather_summary['date'].between(start_date, end_date)
    
    df_weather_sub = df_weather_summary.loc[mask].copy()
    city_scores = df_weather_sub.groupby(["city"]).agg(
        avg_comfort_score=("comfort_score", "mean"),
        checkin_date = ("date" ,"min"),
        checkout_date = ("date","max"),
        rain_sum = ("rain_sum","sum"),
        temp = ("temp_mean","mean"),
        humidity = ("humidity_mean","mean"),
        clear_slots = ("clear_slots_count",'sum'),
        rain_slots = ("rain_slots_count",'sum'),
        wind_speed_max = ("wind_speed_max","max"),
        scraped_at = ("scraped_at","first"),
    ).reset_index()

    # Sort by average comfort score in descending order and select top N cities
    top_cities = city_scores.sort_values("avg_comfort_score", ascending=False)
    top_cities['selected'] = 0
    top_cities.loc[top_cities.index[:top_n], 'selected'] = 1
    #top_cities['checkin_date = start_date']
    return top_cities


    