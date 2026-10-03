# data_access.py
# lecture RDS pour le dashboard (rapide, en cache)
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from config_kayak import RDSHOST, AWS_DB_NAME, AWS_DB_USER, AWS_DB_PASS
from sqlalchemy import text
from rds_utils import get_pg_engine


get_engine = st.cache_resource(get_pg_engine)
# --28/09 base Neon
# @st.cache_resource
# def get_engine():
#     from urllib.parse import quote_plus
#     pwd = quote_plus(AWS_DB_PASS)
#     return create_engine(
#         f"postgresql+psycopg2://{AWS_DB_USER}:{pwd}@{RDSHOST}:5432/{AWS_DB_NAME}",
#         pool_pre_ping=True,
#     )


@st.cache_data(ttl=3600, show_spinner="Chargement des données...")
def load_top_cities() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM cities", get_engine())


@st.cache_data(ttl=3600)
def load_weather() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM weather", get_engine())


@st.cache_data(ttl=3600)
def load_hotels_precomputed() -> pd.DataFrame:
    """Hôtels du dernier run du pipeline (top20 par ville)."""
    return pd.read_sql("SELECT * FROM hotels", get_engine())

@st.cache_data(ttl=600)
def load_search_keys() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT DISTINCT checkin_date, checkout_date, n_adults, n_children, n_rooms FROM hotels",
        get_engine())

#@st.cache_data(ttl=600)
# def load_hotels_for(checkin, checkout, n_adults, n_children, n_rooms) -> pd.DataFrame:
#     q = text("SELECT * FROM hotels WHERE checkin_date=:ci AND checkout_date=:co "
#              "AND n_adults=:a AND n_children=:c AND n_rooms=:r")
#     return pd.read_sql(q, get_engine(),
#                        params={"ci": checkin, "co": checkout, "a": n_adults, "c": n_children, "r": n_rooms})
@st.cache_data(ttl=600)    
def load_hotels_for(checkin, checkout, n_adults, n_children, n_rooms) -> pd.DataFrame:
    """Hôtels d'une recherche, avec lat/lon de la ville (requis par plot_city_hotels)."""
    q = text("""
        SELECT h.*, c.city_lat AS lat_city, c.city_lon AS lon_city
        FROM hotels h
        LEFT JOIN (
            SELECT DISTINCT ON (city_id) city_id, city_lat, city_lon 
            FROM cities
            ORDER BY city_id
            ) c ON c.city_id = h.city_id
        WHERE h.checkin_date = :ci 
          AND h.checkout_date = :co
          AND h.n_adults = :a 
          AND h.n_children = :c
          AND h.n_rooms = :r
    """)
    try:
        return pd.read_sql(q, get_engine(),
                           params={"ci": checkin, "co": checkout, "a": int(n_adults), 
                                   "c": int(n_children), "r": int(n_rooms)})
    except Exception as e:
        st.error(f"Erreur lors du chargement des hôtels : {e}")
        return pd.DataFrame()