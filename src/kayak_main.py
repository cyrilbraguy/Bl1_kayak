# ====================================================================
# Kayak project Cyril 
# module main : 
# kayak_main.py
# (c) 2026-09-20 
# ====================================================================
import os


import config_kayak as config_kayak
from config_kayak import (
    WEATHER_API_KEY, AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_DB_NAME, AWS_DB_USER, AWS_DB_PASS, AWS_REGION,

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
CHECKIN_DATE_NR = 1   # 2nd day of weather forecasts
CHECKOUT_DATE_NR = -1  # last day of weather forecasts


n_adults = 2
n_children = 3
n_rooms = 2
max_results = 5
max_price = 500

from pathlib import Path

from load_cities import load_cities, get_coordinates_cities
from get_weather_forecasts import get_weather, compile_weather2, get_weather_data_for_cities, select_best_weather_cities
from scrap_hotels import collect_cities_hotels, select_top_hotels
from s3_utils import save_csv_to_s3, timestamped_filename, read_csv_from_s3


if __name__ == "__main__":
    # load env variables and init key program variables
    config_kayak
    # 
    print(BASE_URL_NOMINATIM)
    print(AWS_BUCKET_NAME)
    
    # Utilisation typique : chemin indépendant du CWD
    SRC_DIR = Path(__file__).resolve().parent
    BASE_DIR = SRC_DIR.parent
    # print(SRC_DIR)
    # print(BASE_DIR)
    os.chdir(BASE_DIR)
    print(f"CWD apres: {Path.cwd()}")
    # csv_path = BASE_DIR / "cities.csv"   
        
    
    
    # load cities list:
    cities_list_df = load_cities()
    print(cities_list_df.head())
    # get coordinates of cities :
    results_df = get_coordinates_cities(cities_list_df)  
    print(results_df.head())  
    # results_df["city_id"] = results_df.apply(
    #     lambda r: city_id(r["city_name"], r["lat"], r["lon"]), axis=1)

    # save cities data to disk or S3 : 
    #DATA_DIR_CSV = ./json
    results_df.to_csv(os.path.join(DATA_DIR_CSV, "cities.csv"), index=False, encoding="utf-8")
    print("Saved", len(results_df), "rows to", os.path.join(DATA_DIR_CSV, "cities.csv"))
    uri_cities = save_csv_to_s3(results_df, "cities.csv")
    # results_df
    
    # weather forecasts : 
    df_cities = results_df
    result_weather = get_weather_data_for_cities(df_cities)
    print(result_weather.head(10))
    # weather_forecast = get_weather(lat,lon)    
    # print(weather_forecast)
    # df_weather2 = compile_weather2(weather_forecast)

    # print(df_weather2.head())
    
    # select top 7 cities with best weather conditions for next 5 days : 
    df_cities = results_df
    result_weather = get_weather_data_for_cities(df_cities)
    print(result_weather.head())
    date_span = result_weather["date"].unique()
    
    top_cities = select_best_weather_cities(result_weather, top_n=7)
    # merge left with df_cities to get lat/lon for top cities
    top_cities = top_cities.merge(df_cities[['city_name', 'lat', 'lon']], left_on='city', right_on='city_name', how='left')
    top_cities = top_cities.drop(columns=['city_name'])  # Drop the duplicate city_name column after merge
    print(top_cities.head(7))
    
    # save top_cities weather forecasts : 
    uri_weather_top_cities = save_csv_to_s3(top_cities, timestamped_filename("weather_top_cities"))
    
    # scrap booking : 
    
    checkin_date = date_span[CHECKIN_DATE_NR].isoformat()   # "2026-09-22"
    checkout_date = date_span[CHECKOUT_DATE_NR].isoformat() # "2026-09-26"
    print('search hotels for top cities with best weather conditions')
    print(top_cities.loc[top_cities['selected'] == 1, 'city'].tolist())
    print(f"checkin_date: {checkin_date}, checkout_date: {checkout_date}, n_adults: {n_adults}, n_children: {n_children}, n_rooms: {n_rooms}, max_results: {max_results}")

    #from aggregate_hotels import select_top_hotels
    hotels_df = collect_cities_hotels(top_cities, checkin_date, checkout_date, n_adults, n_children, n_rooms, max_results)
    top20_combined = select_top_hotels(hotels_df, n=20, criterion="combined", max_price=max_price)
    
    print("Top 20 hotels (combined score & price):")
    print(top20_combined[["city", "hotel_name", "score", "price", "url","hotel_description","room_description"]])
    
    
    # create datalake using S3 : 
    
    # Depuis un DataFrame (aucun fichier temporaire écrit sur disque)
    uri = save_csv_to_s3(hotels_df, "hotels_top20.csv")
    # -> s3://kayak-cyril/kayak/hotels_top20.csv

    # Depuis un fichier .csv déjà sur disque
    # uri = save_csv_to_s3("hotels_lyon.csv", "hotels_lyon.csv")
    df = read_csv_from_s3(
        AWS_BUCKET_NAME,
        "data/cities.csv",
        sep=",",
        encoding="utf-8",
    )
    print(df.head())
    # # Nom de fichier horodaté (évite d'écraser un upload précédent)
    # uri = save_csv_to_s3(hotels_df, timestamped_filename("hotels"))
    
    
    # ETL process from datalake to postgres database : 
    # read .csv file with cities, weather, hotels 
    # and select top 20 hotels with best score and price

    # transform cities_df to have one row per city with all information about the city, weather, etc.

    # transform hotels_df to have one row per hotel with all information about the hotel and the city, weather, etc.


    # transform weather_df to have one row per time slot per city with all information about the weather and the city, hotels, etc.

    # load cities into AWS RDS database 

    # load hotels in RDS database 

    # load 
        