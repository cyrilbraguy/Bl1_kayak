# pipeline.py (ex-main.py, quasi inchangé, juste wrappé dans une fonction)
import os
import sys
from pathlib import Path
import pandas as pd

from sqlalchemy import create_engine
from sqlalchemy.types import (
    Integer, BigInteger, SmallInteger, Float, Numeric, String, Text,
    Boolean, Date, DateTime,
)

import config_kayak
from config_kayak import (
    AWS_BUCKET_NAME, AWS_BUCKET_DIR, DATA_DIR_CSV, 
    
)
from load_cities import load_cities, get_coordinates_cities
from get_weather_forecasts import (
    get_weather_data_for_cities, 
    select_best_weather_cities, run_weather_searches)
from scrap_hotels import collect_cities_hotels, select_top_hotels
from s3_utils import save_csv_to_s3, timestamped_filename, read_csv_from_s3
from rds_utils import get_rds_engine, save_df_to_rds, get_pg_engine

from availability import build_date_windows, run_hotel_searches, keys_from_df, DEFAULT_OCCUPANCY

CHECKIN_DATE_NR = 1
CHECKOUT_DATE_NR = -1

SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent
os.chdir(BASE_DIR)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))



# Types SQL cibles, par colonne (adapte aux noms de tes colonnes)
DTYPES_CITIES = {
    "city_id":           Text(),
    "city":              Text(),
    "city_lat":          Float(),
    "city_lon":          Float(),
    "city_name_":        Text(),
    "city_plus":         Text(),
}

DTYPES_HOTELS = {
    "city_id":           Text(),
    "city":              String(100),
    "city_name_":        Text(),
    "checkin_date":      Date(),
    "checkout_date":     Date(),
    "n_adults":          SmallInteger(),
    "n_children":        SmallInteger(),
    "n_rooms":           SmallInteger(),
    "scraped_at":        DateTime(),

    "hotel_name":        Text(),
    "url_hotel":         Text(),
    "address_hotel":     Text(),
    "hotel_city":        Text(),
    "hotel_description": Text(),
    "room_description":  Text(),
    "lat_hotel":         Float(),
    "lon_hotel":         Float(),
  
    "score_hotel":       Numeric(10, 2),
    "price_hotel":       Numeric(10, 2),
    "currency_hotel":    Text(),
    "combined_score_hotel": Numeric(10, 2),
}

DTYPES_WEATHER = {
    "city_id":           Text(),
    "city":              Text(),
    #"city_name_":        Text(),
    "checkin_date":      Date(),
    "checkout_date":     Date(),
    "scraped_at":        DateTime(),
    "avg_comfort_score": Numeric(4, 1),
    "temp":              Numeric(5, 2),
    "humidity":          Numeric(5, 2),
    "wind_speed_max":    Numeric(10, 2),
    "clear_slots":       Integer(),
    "rain_slots":        Integer(),
    "rain_sum":          Numeric(10, 2),
    "selected":          Integer(),
    "lat":               Float(),
    "lon":               Float(),
}

def sauver_df(df: pd.DataFrame, table: str, engine, dtypes: dict,
              if_exists: str = "append") -> None:
    """Écrit df en base en forçant les types SQL, avec conversions pandas préalables."""
    out = df.copy()

    # Conversions pandas : sinon une colonne 'object' peut partir en TEXT malgré le dtype
    for col, typ in dtypes.items():
        if col not in out.columns:
            continue
        if isinstance(typ, Date):
            out[col] = pd.to_datetime(out[col]).dt.date
        elif isinstance(typ, DateTime):
            out[col] = pd.to_datetime(out[col])
        elif isinstance(typ, (Integer, SmallInteger, BigInteger)):
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")  # entier nullable
        elif isinstance(typ, (Float, Numeric)):
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # On ne garde dans dtype que les colonnes présentes (sinon erreur)
    dtype_utile = {c: t for c, t in dtypes.items() if c in out.columns}
    out.to_sql(table, engine, if_exists=if_exists, index=False,
               dtype=dtype_utile, method="multi", chunksize=1000)


# Utilisation


# *** 

def run_pipeline(
    n_adults: int = 2,
    n_children: int = 3,
    n_rooms: int = 2,
    max_results: int = 5,
    max_price: float = 500,
    force: bool = False
) -> dict:
    """Exécute le pipeline complet : villes -> météo -> hôtels -> S3 -> RDS.
    Retourne un résumé pour logging/monitoring."""
    # 1. get cities and get coord & save to s3
    scraped_dt = pd.Timestamp.now()  # scraped_datetime added 01/10/2026
    cities_list_df = load_cities()
    results_df = get_coordinates_cities(cities_list_df)
    results_df.to_csv(os.path.join(DATA_DIR_CSV, "cities.csv"), index=False, encoding="utf-8")
    save_csv_to_s3(results_df, "cities.csv")

    # 2. get weather data on 5 days free formula 
    df_cities = results_df
    # scraped_dt
    result_weather = get_weather_data_for_cities(df_cities, scraped_dt = scraped_dt)
    result_weather['scraped_at'] = scraped_dt
    
    # 3 make Weather summary on different time windows (for trip)
    # build different time windows for weather and hotels search target
    windows = build_date_windows(result_weather["date"].unique())
    
    date_span = result_weather["date"].unique()
    checkin_date = date_span[CHECKIN_DATE_NR].isoformat()
    checkout_date = date_span[CHECKOUT_DATE_NR].isoformat()

    # top_cities = select_best_weather_cities(
    #     result_weather, top_n=5, start_date=checkin_date, end_date=checkout_date
    # )
    engine = get_pg_engine() #use engine with default DATABASE_URL default variable
    
        
    top_cities = run_weather_searches(
                    result_weather, windows,
                    select_weather_cities_fn = select_best_weather_cities,
                    scraped_dt = scraped_dt,
                    top_n = 5,
                    )
    print(f"top cities before \n {top_cities}")
    
    top_cities = top_cities.merge(
        df_cities.drop(columns=["lat", "lon"]), how="left", left_on="city", right_on="city_name"
    )
    top_cities = top_cities.drop(columns=["city_name"]).rename(
        columns={"lat": "lat_city", "lon": "lon_city"}
    )
    top_cities.to_csv(os.path.join(DATA_DIR_CSV, "top_weather_cities.csv"), index=False, encoding="utf-8")
    save_csv_to_s3(top_cities, timestamped_filename("weather_top_cities"))

    print(f"after:\n {top_cities.head()}")

    # engine SQL base :
    
    try:
        existing = keys_from_df(pd.read_sql(
            "SELECT DISTINCT checkin_date, checkout_date, n_adults, n_children, n_rooms FROM hotels",
            engine))
    except Exception as e:
        print(f"Lecture des recherches existantes impossible ({e}) : on part de zéro")
        existing = set()

    
    
    # Hotels search new version :
    hotels_all, failed = run_hotel_searches(
        top_cities, windows, DEFAULT_OCCUPANCY,
        collect_fn=collect_cities_hotels, select_fn=select_top_hotels,
        skip_keys=existing, max_results=max_results, max_price=max_price,
        scraped_dt = scraped_dt,
        force = force,
    )
    if failed:
        print(f"Recherches en échec : {failed}")
    if hotels_all.empty:
        print("Rien de nouveau à scraper : arrêt.")
        return {"n_hotels": 0, "n_failed": len(failed)}

    hotels_all = hotels_all.rename(columns={
        "url": "url_hotel", "address": "address_hotel", "latitude": "lat_hotel",
        "longitude": "lon_hotel", "score": "score_hotel", "price": "price_hotel",
        "currency": "currency_hotel", "combined_score": "combined_score_hotel",
    })
    save_csv_to_s3(hotels_all, timestamped_filename("hotels_windows"))  # datalake : toutes les fenêtres

    # end mod scenario pre_select
    
    # --mod 28/09 : switch to scenario pre_select
    # cities_top20_hotels = top_cities.merge(
    #     top20_hotels_combined, how="outer", left_on="city_name", right_on="city",
    #     suffixes=["_city", "_hotel"],
    # )
    # ++ 28/09 scenario pre_select
    cities_top20_hotels = top_cities.merge(
            hotels_all.drop(columns=["checkin_date", "checkout_date"]),  # <- seul changement
        how="outer", left_on="city_name_", right_on="city",
        suffixes=["_city", "_hotel"],
        )
    # end ++
    cities_top20_hotels = cities_top20_hotels.sort_values("combined_score_hotel", ascending=False)
    cities_top20_hotels = cities_top20_hotels.rename(columns={"city_city": "city","scraped_at_city":"scraped_at"}).drop(columns=["city_hotel"])

    print(f"top cities et top20 hotels:\n {cities_top20_hotels}")

    cities_top20_hotels.to_csv(os.path.join(DATA_DIR_CSV, "hotels_top20_cities.csv"), index=False, encoding="utf-8")
    save_csv_to_s3(cities_top20_hotels, "hotels_top20cities.csv")

    df = read_csv_from_s3(AWS_BUCKET_NAME, f"{AWS_BUCKET_DIR}/hotels_top20cities.csv", sep=",", encoding="utf-8")

    cities_cols = ["city_id", "city", "city_lat", "city_lon", "city_name_", "city_plus"]
    
    hotels_cols = [  #++ 28/09
        "city_id", "city", "city_name_", "checkin_date", "checkout_date", "n_adults", "n_children", "n_rooms",
        "scraped_at", "hotel_name", "url_hotel", "address_hotel","hotel_city", "hotel_description",
        "lat_hotel", "lon_hotel", "score_hotel", "price_hotel", "currency_hotel",
        "room_description", "combined_score_hotel"
    ]
    
    # hotels_cols = ["city", "city_id", "checkin_date", "checkout_date", "hotel_name", "url_hotel",
    #                "address_hotel", "hotel_description", "lat_hotel", "lon_hotel", "score_hotel",
    #                "price_hotel", "currency_hotel", "room_description", "combined_score_hotel", "hotel_city"]
    weather_cols = ["city_id", "city", "checkin_date", "checkout_date", "scraped_at", "avg_comfort_score", "temp",
                     "humidity", "wind_speed_max", "clear_slots", "rain_slots", "rain_sum", "selected","city_lat", "city_lon"]

    weather_rename = {"city_lat":"lat",
                      "city_lon":"lon"}
    df_cities2 = df[cities_cols].dropna().drop_duplicates()
    
    # -- 28/09
    df_hotels2 = df[hotels_cols].dropna().drop_duplicates()
    # ++
    # df_hotels2 = hotels_all.merge(
    #     top_cities[["city", "city_id"]].drop_duplicates(), on="city", how="left"
    # )
    # hotels_cols = [c for c in hotels_cols if c in df_hotels2.columns]
    # df_hotels2 = (
    #     df_hotels2[hotels_cols]
    #     .dropna(subset=["city_id", "hotel_name", "checkin_date", "checkout_date"])
    #     .drop_duplicates()
    # )
    # end ++
    df_weather2 = df[weather_cols].rename(columns=weather_rename).dropna().drop_duplicates()

    
    try:
        # save_df_to_rds(df_cities2, "cities", engine, if_exists="append")
        # save_df_to_rds(df_hotels2, "hotels", engine, if_exists="append")
        # save_df_to_rds(df_weather2, "weather", engine, if_exists="append")
        
        # exemple avec DTYPES :
        # sauver_df(df_hotels, "hotels", engine, DTYPES_HOTELS)
        df_cities2.to_sql(name="cities",con=engine,if_exists="replace",index=False, dtype=DTYPES_CITIES)
        df_hotels2.to_sql(name="hotels",con=engine,if_exists="replace",index=False, dtype=DTYPES_HOTELS)
        df_weather2.to_sql(name="weather",con=engine,if_exists="replace",index=False, dtype=DTYPES_WEATHER)
        
        
    finally:
        engine.dispose()

    return {"n_cities": len(df_cities2), "n_hotels": len(df_hotels2), "n_weather": len(df_weather2)}


if __name__ == "__main__":
    summary = run_pipeline(
        max_results = 6,
        max_price = 300,
        force=True)
    print(summary)