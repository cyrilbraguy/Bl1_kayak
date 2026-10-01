# ====================================================================
# Kayak project Cyril 
# module 1 : 
# config_kayak.py 
# (c) 2026-09-20 
# ====================================================================

import json
from dotenv import load_dotenv
import os
import sys
from pathlib import Path

import requests
import pandas as pd
import warnings
import logging  # for logging debug messages
import json
import random
import time

from django.conf.locale import de

SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# activate debug messages 
logger = logging.getLogger(__name__)

config_cities_list = ["Mont Saint Michel",
"St Malo",
"Bayeux",
"Le Havre",
"Rouen",
"Paris",
"Amiens",
"Lille",
"Strasbourg",
"Chateau du Haut Koenigsbourg",
"Colmar",
"Eguisheim",
"Besancon",
"Dijon",
"Annecy",
"Grenoble",
"Lyon",
"Gorges du Verdon",
"Bormes les Mimosas",
"Cassis",
"Marseille",
"Aix en Provence",
"Avignon",
"Uzes",
"Nimes",
"Aigues Mortes",
"Saintes Maries de la mer",
"Collioure",
"Carcassonne",
"Ariege",
"Toulouse",
"Montauban",
"Biarritz",
"Bayonne",
"La Rochelle"]

# parameters setting 

load_dotenv()
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY= os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_BUCKET_DIR = os.getenv("AWS_BUCKET_DIR")
AWS_DB_NAME = os.getenv("AWS_DB_NAME")
AWS_DB_USER = os.getenv("AWS_DB_USER")
AWS_DB_PASS = os.getenv("AWS_DB_PASS")
AWS_REGION = os.getenv("AWS_REGION")
RDSHOST = os.getenv("RDSHOST")
DATABASE_URL = os.getenv("DATABASE_URL")

BASE_URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
BASE_URL_OPENWEATHERMAP = "https://api.openweathermap.org/data/2.5"

CONFIG_CITIES_FILE = "cities.csv"
MAX_CITIES_NUMBER = 35

DATA_DIR = f"{BASE_DIR}/data"
DATA_DIR_CONFIG = f"{DATA_DIR}/config"
os.makedirs(DATA_DIR_CONFIG, exist_ok=True)

DATA_DIR_CSV = f"{DATA_DIR}/csv"
os.makedirs(DATA_DIR_CSV, exist_ok=True)

DATA_DIR_HTML = f"{DATA_DIR}/html"
os.makedirs(DATA_DIR_HTML, exist_ok=True)

DATA_DIR_JSON = f"{DATA_DIR}/json"
os.makedirs(DATA_DIR_JSON, exist_ok=True)

DATA_DIR_JSON_CITIES = f"{DATA_DIR_JSON}/cities"
os.makedirs(DATA_DIR_JSON_CITIES, exist_ok=True)

DATA_DIR_JSON_HOTELS = f"{DATA_DIR_JSON}/hotels"
os.makedirs(DATA_DIR_JSON_HOTELS, exist_ok=True)

VALID_TYPES = {"city", "town", "village", "hamlet", "municipality", "islet", "historic", "tourism", "county", "gorge"}

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

HEADERS = {'User-Agent': USER_AGENT}
DEFAULT_PARAMS = {"format": "json"}


# save first cities list to .csv (uncomment to save your first file !): 
# cities_list_df = pd.DataFrame({'city_name':config_cities_list})
# cities_list_df.to_csv (f"{DATA_DIR_CONFIG}/cities.csv",index=False, header=False)
print(BASE_URL_NOMINATIM)
