# ====================================================================
# Kayak project Cyril 
# module 2 : 
# load_cities.py 
# (c) 2026-09-20 
# ====================================================================
"""
load cities 

Raises:
    ValueError: _description_

Returns:
    _type_: _description_
"""

import config_kayak as config_kayak
from config_kayak import (
    WEATHER_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_DB_NAME, AWS_DB_USER, AWS_DB_PASS, AWS_REGION,

    BASE_URL_NOMINATIM,
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

import json
from dotenv import load_dotenv
import os
import requests
import pandas as pd
import warnings
import logging  # for logging debug messages
import json
import random
import time
import logging

# search gps coordinates for the 35 cities : 
logger = logging.getLogger(__name__)


def load_cities()-> pd.DataFrame :
    """load cities from a file or directly inside the function
    with column ['city_name']
    35 bst cities to visit in France
    """
    
    cities_list = pd.read_csv(f"{DATA_DIR_CONFIG}/{CONFIG_CITIES_FILE}",
                              header=None, names = ['city_name'])
    cities_list['city_name_plus'] = (
    cities_list["city_name"]
    .str.replace("'", "+", regex=False)
    .str.replace(" ", "+", regex=False)
    .str.replace("_", "+", regex=False)
    )
    
    cities_list['city_name_'] = (
        cities_list["city_name_plus"]
        .str.replace("+", "_", regex=False)
    )
    
    # add warning if more than 35 cities
    if len(cities_list)>MAX_CITIES_NUMBER:
        msg = f"More than {MAX_CITIES_NUMBER} in cities file from {DATA_DIR_CONFIG}/{CONFIG_CITIES_FILE}"
        warnings.warn(msg, UserWarning, stacklevel=2)
    return cities_list

def clean_name(name):
    """ clean name of city for name of file saving and city_id string
    replace "+" "'" & space by "_" 
    """
    name = name.replace(" ","_")
    name = name.replace("'",'_')
    name = name.replace('+','_')
    return name
    

def plus_name(name):
    """ plus name of city for search & query activities
    replace "_" "'" & space by "+" 
    """
    name = name.replace("'",'+')
    name = name.replace(" ","+")
    name = name.replace('_','+')
    return name

def _get_city_properties(data: list) -> dict | None:
    """get proper item in data from big json delivered by nominatim
    to extract later lat + lon properties  """
    for item in data:
        if item.get("addresstype") in VALID_TYPES:
            return item
    return None

def save_to_cache(city_name_: str, data):
    filename = f"{city_name_}.json"
    p = os.path.join(DATA_DIR_JSON_CITIES, filename)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def _cache_lookup(city_name_: str):
    """Return path of existing cache file for city_name_, or None."""
    p = os.path.join(DATA_DIR_JSON_CITIES, f"{city_name_}.json")
    return p if os.path.exists(p) else None


def load_from_cache(city_name_: str):
    """Load city data from json file if exists in cache dir."""
    
    data = _cache_lookup(city_name_)
    if data:
        with open(data, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return None
    return None

def clean_cities_names(cities_list):
    cleaned_cities_list = []
    for city in cities_list:
        city_enc =city.replace(' ','+')
        cleaned_cities_list.append(city_enc)
    return cleaned_cities_list

def extract_coordinates(data, feature_index=0):
    """Extrait les coordonnées [lon, lat] d'une feature GeoJSON."""
    try:
        coords = data["features"][feature_index]["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        return lon, lat
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Impossible d'extraire les coordonnées: {e}")

# # Depuis un fichier
# with open("data.json", "r", encoding="utf-8") as f:
#     data = json.load(f)

# lon, lat = extract_coordinates(data, feature_index=0)
# print(f"Longitude: {lon}, Latitude: {lat}")

# Bonus : extraire toutes les features avec leur nom
def extract_all_coordinates(data):
    """Retourne une liste de (nom, lon, lat) pour toutes les features."""
    results = []
    for feat in data.get("features", []):
        try:
            name = feat["properties"].get("name", "N/A")
            lon, lat = feat["geometry"]["coordinates"]
            results.append((name, lon, lat))
        except (KeyError, TypeError):
            continue
    return results

def get_nominatim(city_cleaned:str, delay:int = 1.82, max_retries: int = 3, timeout: int = 10):
    """ get city coordinates from nominatim api 
    city_cleaned : str : spaces replaced by '+' 
    delay : delay from request order , default is 1.82 s 
    """

    params = DEFAULT_PARAMS.copy()
    params['q'] = city_cleaned
    params['countrycodes'] = 'fr'
    for attempt in range(max_retries):
        try:
            
            response = requests.get(
                url = BASE_URL_NOMINATIM, 
                headers = HEADERS,
                params = params, 
                timeout=10            
                )
        except (requests.exceptions.Timeout, 
                requests.exceptions.CorrectionError) as e:
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            print(f"[get_nominatim] échec après {max_retries} tentatives ({city_cleaned!r}) : {e}")
            return None
        status = response.status_code
    
        if status == 200:
            try:
                data = response.json()
            except ValueError:
                data = None
            time.sleep(delay)
            
            return data or None
            
        if status == 429 or status >= 500:
            wait = delay *2 + random.uniform(0,0.52) 
            if attempt < max_retries -1:
                time.sleep(wait)
                continue
            return None
    
        # others codes (400, 403) : no retry , error is definitive
        return None
    return None
      
       

"""
Génération d'un identifiant stable et déterministe par ville, à utiliser
comme clé primaire/étrangère en base de données.
"""

import re
import unicodedata
import uuid
from typing import Optional


def slugify(text: str) -> str:
    """Convertit un texte en slug ASCII minuscule : accents retirés,
    espaces/apostrophes remplacés par '-', caractères non alphanumériques
    supprimés. Ex. "Saint-Étienne" -> "saint-etienne"."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def city_id(city_name: str, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
    """
    ID stable et lisible pour une ville — RECOMMANDÉ pour ton cas (liste
    restreinte de villes avec coordonnées déjà disponibles dans top_cities).

    - Sans coordonnées : city_id("Collioure") -> "collioure"
      Suffisant si tu es sûr qu'il n'y a pas d'homonymes dans ta liste.
    - Avec coordonnées (recommandé) : désambiguïse automatiquement les
      homonymes (ex. plusieurs "Saint-Martin" en France) sans registre
      externe à maintenir.
      city_id("Saint-Martin", 42.52, 3.08) -> "saint-martin-4252-0308"

    Déterministe : le même nom + mêmes coordonnées (arrondies à 2 décimales,
    soit ~1 km de précision) redonnent toujours le même ID d'un run à l'autre
    -> permet un upsert propre en base plutôt que des doublons.
    """
    base = slugify(city_name)
    if latitude is None or longitude is None:
        return base
    lat_part = f"{latitude:.2f}".replace(".", "").replace("-", "m")
    lon_part = f"{longitude:.2f}".replace(".", "").replace("-", "m")
    return f"{base}-{lat_part}-{lon_part}"


# --- Bonus : alternative en UUID opaque (déterministe aussi) ---------------
# Utile si ta base impose des clés UUID plutôt que des chaînes lisibles.
_CITY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "booking-scraper.cities")


def city_uuid(city_name: str) -> str:
    """UUID déterministe basé sur le nom normalisé (sans accents/casse).
    Même ville -> même UUID à chaque exécution, sans dépendre de coordonnées."""
    normalized = slugify(city_name)
    return str(uuid.uuid5(_CITY_NAMESPACE, normalized))



# cleaned_cities = clean_cities_names(cities_list)
# print(cleaned_cities)
def get_coordinates_cities(cities_list_df) -> pd.DataFrame:
    """ get coordinates for all cities from dataframe to dataframe """
    results = []
    for idx,row in cities_list_df.iterrows():
        city = row['city_name']
        city_ = row['city_name_']
        city_plus = row['city_name_plus']
        
        # city = row['city_name']
        
        # city_plus = row['city_name_plus']
        # city_ = row['city_name_']
        
        #https://nominatim.openstreetmap.org/search?<params>
        #city_enc =city.replace(' ','+')
        # params = "?q="+city
        # format = "&format=geojson"
        # input_url = gps_url+params+format
        # print(input_url)
        #response = requests.get(input_url)
        
        # read from cache if city is already there 
        # if yes : take data from cache in same json format as direct call from nominatim: 
        data = load_from_cache(city_)
        if data is None:
        # else : get coordinates:
            data = get_nominatim(city_plus)
            
        if data:
            save_to_cache(city_,data)
            # print for debug
            logger.debug("%s coord : %s", city, data)   # <-- remplace print()
    
            # save data in cache :
            item = _get_city_properties(data)
            if item:
                results.append({
                    "city_name"  : city,
                    "city_name_" : city_,
                    "city_plus"  : city_plus,
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    
                })
            else:
                # item is None : 
                results.append({
                                    "city_name"  : city,
                                    "city_name_" : city_,
                                    "city_plus"  : city_plus,
                                    "lat": None,
                                    "lon": None
                            })
        else:
            # data is none : report error in reading coordinates 
            results.append({
                    "city_name"  : city,
                    "city_name_" : city_,
                    "city_plus"  : city_plus,
                    "lat": None,
                    "lon": None
            })
               
    results_df = pd.DataFrame(results)
    results_df["city_lat"] = pd.to_numeric(results_df["lat"], errors="coerce")
    results_df["city_lon"] = pd.to_numeric(results_df["lon"], errors="coerce")
    results_df["city_id"] = results_df.apply(
            lambda r: city_id(r["city_name"], r["city_lat"], r["city_lon"]), axis=1)
    return results_df
   

# if __name__ == "__main__":
#     # Exemple d'application à un DataFrame top_cities (colonnes: city, lat, lon)
#     import pandas as pd

#     top_cities = pd.DataFrame({
#         "city": ["Lyon", "Annecy", "Collioure"],
#         "lat": [45.7578137, 45.8992348, 42.52505],
#         "lon": [4.8320114, 6.1288847, 3.0831554],
#     })
#     top_cities["city_id"] = top_cities.apply(
#         lambda r: city_id(r["city"], r["lat"], r["lon"]), axis=1
#     )
#     print(top_cities