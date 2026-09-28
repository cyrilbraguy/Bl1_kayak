# hotels_live.py
#recherche interactive isolée du batch

import streamlit as st
import pandas as pd
from scrap_hotels import collect_cities_hotels, select_top_hotels


@st.cache_data(ttl=1800, show_spinner="Recherche des hôtels...")
def search_hotels(
    top_cities: pd.DataFrame,
    checkin_date: str,
    checkout_date: str,
    n_adults: int,
    n_children: int,
    n_rooms: int,
    max_results: int = 5,
) -> pd.DataFrame:
    """Version dashboard : ne réécrit rien en RDS, retourne juste le résultat."""
    hotels_df = collect_cities_hotels(
        top_cities, checkin_date, checkout_date, n_adults, n_children, n_rooms, max_results
    )
    return select_top_hotels(hotels_df, n=20, criterion="combined", out_all=True).rename(
        columns={"url": "url_hotel", "address": "address_hotel", "latitude": "lat_hotel",
                 "longitude": "lon_hotel", "score": "score_hotel", "price": "price_hotel",
                 "currency": "currency_hotel", "combined_score": "combined_score_hotel"}
    )