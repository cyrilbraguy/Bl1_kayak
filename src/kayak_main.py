# ====================================================================
# Kayak project Cyril 
# module main : 
# kayak_main.py
# (c) 2026-09-20 
# ====================================================================
import os
import sys

import config_kayak as config_kayak
from config_kayak import (
    WEATHER_API_KEY, AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_DB_NAME, AWS_DB_USER, AWS_DB_PASS, AWS_REGION,
    RDSHOST,

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
max_results = 2    #nb max hotels found per city
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
    
    # add /src in path 
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))  # insert(0, ...) : priorité sur les autres chemins    
    
    
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
    
    date_span = result_weather["date"].unique()
    checkin_date = date_span[CHECKIN_DATE_NR].isoformat()   # "2026-09-22"
    checkout_date = date_span[CHECKOUT_DATE_NR].isoformat() # "2026-09-26"
    
    top_cities = select_best_weather_cities(result_weather, top_n=7,
                                            start_date=checkin_date,
                                            end_date=checkout_date)
    # merge left with df_cities to get lat/lon for top cities
    
    print(f"top cities before \n {top_cities}")
    top_cities = top_cities.merge(df_cities.drop(columns=['lat','lon']),how='left',left_on='city',right_on='city_name')
    top_cities = top_cities.drop(columns=['city_name'])
    top_cities = top_cities.rename(columns={'lat':'lat_city','lon':'lon_city',})
    print(f"after:\n {top_cities.head()}")
    
    
    # save top_cities weather forecasts : 
    top_cities.to_csv(os.path.join(DATA_DIR_CSV, "top_weather_cities.csv"), index=False, encoding="utf-8")
        
    uri_weather_top_cities = save_csv_to_s3(top_cities, timestamped_filename("weather_top_cities"))
    
    # scrap booking : 
    print('search hotels for top cities with best weather conditions')
    print(top_cities.loc[top_cities['selected'] == 1, 'city'].tolist())
    print(f"checkin_date: {checkin_date}, checkout_date: {checkout_date}, n_adults: {n_adults}, n_children: {n_children}, n_rooms: {n_rooms}, max_results: {max_results}")

    #from aggregate_hotels import select_top_hotels
    hotels_df = collect_cities_hotels(top_cities, checkin_date, checkout_date, 
                                      n_adults, n_children, n_rooms, max_results)
    top20_hotels_combined = select_top_hotels(
        hotels_df, n=20, 
        criterion="combined", 
        max_price=max_price,
        out_all=True)
    
    top20_hotels_combined= top20_hotels_combined.rename(
        columns={'url':'url_hotel',
                 'address':'address_hotel',
                 'latitude':'lat_hotel',
                 'longitude':'lon_hotel',
                 'score':'score_hotel',
                 'price':'price_hotel',
                 'currency':'currency_hotel',
                 'combined_score':'combined_score_hotel'})
    
    print("Top 20 hotels (combined score & price):")
    filter_cols = ["city", "hotel_name", "score_hotel", "price_hotel", 
                   'combined_score_hotel',"hotel_description",
                   "room_description"] 
    
    print(top20_hotels_combined[filter_cols])
    
    
    
    cities_top20_hotels= top_cities.merge(
        top20_hotels_combined,
        how='outer',
        left_on='city_name_',
        right_on='city',
        suffixes=['_city','_hotel'])
    
    cities_top20_hotels = cities_top20_hotels.sort_values('combined_score_hotel',ascending=False)
    cities_top20_hotels = cities_top20_hotels.rename(
    columns = {'city_city':'city'}).drop(
    columns=['city_hotel'])
    print(f"top cities et top20 hotels:\n {cities_top20_hotels}")
    
    # create datalake using S3 : 
    cities_top20_hotels.to_csv(os.path.join(DATA_DIR_CSV, "hotels_top20_cities.csv"), index=False, encoding="utf-8")
    # Depuis un DataFrame (aucun fichier temporaire écrit sur disque)
    uri = save_csv_to_s3(cities_top20_hotels, 
                         "hotels_top20cities.csv")
    # timestamped_filename()
    # -> s3://kayak-cyril/kayak/hotels_top20.csv
    

    # ======== ETL PROCESS FROM S3 to SQL db ============
    # Depuis un fichier .csv déjà sur disque
    
    # ETL process from datalake to postgres database : 
        # read .csv file with cities, weather, hotels 
        # and select top 20 hotels with best score and price
        
    # uri = save_csv_to_s3("hotels_lyon.csv", "hotels_lyon.csv")
    df = read_csv_from_s3(
        AWS_BUCKET_NAME,
        f"{AWS_BUCKET_DIR}/hotels_top20cities.csv",
        sep=",",
        encoding="utf-8",
    )
    print(df.head())
    # # Nom de fichier horodaté (évite d'écraser un upload précédent)
    # uri = save_csv_to_s3(hotels_df, timestamped_filename("hotels"))
    cities_cols = ['city_id','city','city_lat','city_lon','city_name_','city_plus']
    
    hotels_cols = ['city','city_id','checkin_date','checkout_date','hotel_name','url_hotel','address_hotel','hotel_description',
                   'lat_hotel',	'lon_hotel','score_hotel','price_hotel','currency_hotel',
                   'room_description','combined_score_hotel','hotel_city']
    weather_cols = ['city_id','city','checkin_date','checkout_date',
                    'avg_comfort_score','temp','humidity','wind_speed_max', 
                    'clear_slots', 'rain_slots',
                    'rain_sum', 'selected']
    
    df_cities2 = df[cities_cols].dropna().drop_duplicates()
    df_hotels2 = df[hotels_cols].dropna().drop_duplicates()
    df_weather2 = df[weather_cols].dropna().drop_duplicates()
    
    

    # transform cities_df to have one row per city with all information about the city, weather, etc.

    # transform hotels_df to have one row per hotel with all information about the hotel and the city, weather, etc.


    # transform weather_df to have one row per time slot per city with all information about the weather and the city, hotels, etc.

    # RDS engine : 
    import os
    from rds_utils import get_rds_engine, save_df_to_rds

    engine = get_rds_engine(
        host= RDSHOST,       # ex: mydb.xxxxx.eu-west-3.rds.amazonaws.com
        database= AWS_DB_NAME,
        user = AWS_DB_USER,
        password= AWS_DB_PASS,
        port= 5432,
        driver= "postgresql+psycopg2",
    )
    save_df_to_rds(df_cities2, "cities", engine, if_exists="append")
    save_df_to_rds(df_hotels2, "hotels", engine, if_exists="append")
    save_df_to_rds(df_weather2, "weather", engine, if_exists="append")
        
        
    # load cities into AWS RDS database 

    # load hotels in RDS database 

    # load 
        