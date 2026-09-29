# ====================================================================
# Kayak project Cyril 
# module 4 : 
# scrap_hotels.py
# (c) 2026-09-20 
# ====================================================================

### Scrape Booking.com 

# Since BookingHoldings doesn't have aggregated databases, it will be much faster to scrape data directly from booking.com 

# You can scrap as many information asyou want, but we suggest that you get at least:

# *   hotel name,
# *   Url to its booking.com page,
# *   Its coordinates: latitude and longitude
# *   Score given by the website users
# *   Text description of the hotel

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

from load_cities import clean_name
import re
import importlib
import pandas as pd
import booking_scraper_init
importlib.reload(booking_scraper_init)
from booking_scraper_init import get_hotel_availability, get_hotel_availability_sync

def save_city_hotel(city_name_: str, data):
    filename = f"{city_name_}_hotels.json"
    p = os.path.join(DATA_DIR_JSON_HOTELS, filename)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)    


from typing import Optional

import glob
import json
import os
from typing import Literal, Optional, Union
 



#clean data/json/hotels before new search
# gestion des erreurs :
def extract_city(address: str) -> str | None:
    """Extrait la ville : entre ', CODE_POSTAL ' et la virgule suivante."""
    if not address:
        return None
    else:
        
        match = re.search(r",\s*\d{5}\s+([^,]+),", address)
        return match.group(1).strip() if match else None    


def collect_cities_hotels(top_cities,
                          checkin_date: str,
                         checkout_date: str,
                         n_adults: int = 2,
                         n_children: int = 0,
                         n_rooms: int = 1,
                         max_results: int = 20) -> pd.DataFrame:
    
    results_hotels = []

    for city in top_cities.loc[top_cities['selected'] == 1, 'city']:
        print(f"Searching hotels in {city}...")
        try:
            results = get_hotel_availability_sync(
                    city=city,
                    checkin_date=checkin_date,
                    checkout_date=checkout_date,
                    group_adults=n_adults,
                    group_children = n_children,
                    no_rooms=n_rooms,
                    max_results=max_results,
                )
        except Exception as e:
            print(f"Erreur pour {city} : {e}")
            continue # keep results already collected and go to next city
        city_name_ = clean_name(city) 
        # store all json results with {city}_hotels
        for h in results:
            h["city"] = city_name_
        
       
        save_city_hotel(city_name_, results)   # backup JSON individuel
        results_hotels.extend(results)         # <-- extend, pas append, et pas de réassignation

        print(json.dumps(results, ensure_ascii=False, indent=2))
        
    

    hotels_df = pd.DataFrame(results_hotels)
    hotels_df = hotels_df.drop_duplicates(subset="url", keep="first").reset_index(drop=True)
    
    # extract hotel's city from address
    hotels_df['hotel_city'] = hotels_df['address'].apply(extract_city).fillna("")
    
       
        
    return hotels_df

 
def select_top_hotels(
    df: pd.DataFrame,
    n: int = 20,
    criterion: Literal["score", "price", "combined"] = "combined",
    max_price: Optional[float] = None,
    out_all: Optional[bool] = False,
    ) -> pd.DataFrame:
    """
    Sélectionne les n meilleurs hôtels parmi toutes les villes, selon le
    critère choisi :
    - "score"    : meilleur score utilisateur d'abord (décroissant)
    - "price"    : prix le plus bas d'abord (croissant)
    - "combined" : parmi les hôtels avec price <= max_price, meilleur score
                   d'abord (décroissant)
 
    Les lignes sans 'score' ou 'price' (extraction ayant échoué) sont
    écartées avant classement.
 
    Lève ValueError si `criterion` est invalide, si 'combined' est demandé
    sans `max_price`, ou si les colonnes 'score'/'price' sont absentes.
    """
    # define penality : 
    p = (10-0)/1  # (score_max - score_min)/(min unity of price : 1 €)
    
    if criterion not in ("score", "price", "combined"):
        raise ValueError(f"criterion invalide : {criterion!r} (attendu 'score', 'price' ou 'combined')")
    if criterion == "combined" and max_price is None:
        raise ValueError("max_price est requis pour le critère 'combined'")
 
    missing = {"score", "price"} - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans le DataFrame : {missing}")
 
    clean = df.dropna(subset=["score", "price"]).copy()
    if out_all:
        df['combined_score'] = df['score'] - p * (df['price'] - max_price).clip(lower=0)
        df = df.sort_values("combined_score", ascending=False)
        return df.reset_index(drop=True)
    
    else:  # default option : out_all=False
        if criterion == "score":
            ranked = clean.sort_values("score", ascending=False)
        elif criterion == "price":
            ranked = clean.sort_values("price", ascending=True)
        else:  # combined
            ranked = clean[clean["price"] <= max_price].sort_values("score", ascending=False)
    
        return ranked.head(n).reset_index(drop=True)
 
    