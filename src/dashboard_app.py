"""
Dashboard Streamlit - Kayak : Plan your trip from weather forecasts
=====================================================================
Lancement : streamlit run dashboard_app.py

ATTENTION : adapte les imports ci-dessous à l'organisation réelle
de ton projet (modules définis dans ton main.py / src/).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# --- Rend les modules du projet importables (ajuste SRC_DIR si besoin) ---
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = f"{BASE_DIR}/src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- Imports des fonctions métier existantes : À ADAPTER ---
# scrap_hotels(checkin, checkout, n_adults, n_children, n_rooms) -> DataFrame hôtels
# get_weather_summary() -> DataFrame colonnes [date, city, lat, lon, avg_comfort_score, selected]
try:
    # from data_access import load_top_cities, load_weather
    # from hotels_live import search_hotels
    from datetime import date
    from data_access import load_search_keys, load_hotels_for, load_top_cities, load_weather
    from date_picker import render_date_picker, render_search_action
    from availability import keys_from_df, to_date, DEFAULT_OCCUPANCY
except ImportError as e:
    st.error(
        f"Import impossible : {e}\n\n"
        "Vérifie que 'scrap_hotels' et 'get_weather_summary' existent bien "
        "dans tes modules, et adapte le chemin SRC_DIR en haut du fichier."
    )
    st.stop()


st.set_page_config(page_title="Kayak - Plan your trip", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Fonctions de plot (adaptées : retournent fig au lieu de fig.show())
# ============================================================



COLS_TOP_CITIES = ["city", "lat", "lon", "avg_comfort_score", "selected"]




def build_top_cities(weather: pd.DataFrame, cities: pd.DataFrame,
                     checkin=None, checkout=None) -> pd.DataFrame:
    """Villes de la carte météo pour la fenêtre (checkin, checkout) choisie.

    Sans dates : retombe sur le dernier run (comportement d'origine).
    """
    vide = pd.DataFrame(columns=COLS_TOP_CITIES)
    if weather is None or weather.empty:
        return vide
    try:
        w = weather.copy()
        # Normalisation des types pour comparer date / datetime / Timestamp sans surprise
        #w["checkin_date"] = pd.to_datetime(w["checkin_date"]).dt.date
        
        w["checkin_date"] = w["checkin_date"].map(to_date)
        checkin = to_date(checkin) if checkin is not None else w["checkin_date"].max()
        w = w[w["checkin_date"] == checkin]

        if checkout is not None and "checkout_date" in w.columns:
            w["checkout_date"] = w["checkout_date"].map(to_date)
            w = w[w["checkout_date"] == to_date(checkout)]
                
        # if checkin is None:
        #     checkin = w["checkin_date"].max()
        # w = w[w["checkin_date"] == pd.Timestamp(checkin).date()]

        # # Filtre sur le check-out si la colonne existe dans la table weather
        # if checkout is not None and "checkout_date" in w.columns:
        #     w["checkout_date"] = pd.to_datetime(w["checkout_date"]).dt.date
        #     w = w[w["checkout_date"] == pd.Timestamp(checkout).date()]

        if w.empty:
            return vide

        coords = cities.drop_duplicates("city_id")[["city_id", "city_lat", "city_lon"]]
        return (
            w.drop_duplicates("city_id")
             .merge(coords, on="city_id", how="left")
             .dropna(subset=["lat", "lon"])
             .drop(columns=["city_lat", "city_lon"])
        )
    except Exception as e:
        st.error(f"Erreur de filtrage des villes : {e}")
        return vide

def plot_France_cities(top_cities: pd.DataFrame):
    """Carte des villes de France avec indice de confort météo."""
    df = top_cities.copy()
    df["marker_size"] = df["selected"].map({1: 15, 0: 5}).fillna(5)
    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        size="marker_size",
        size_max=20,
        hover_name="city",
        hover_data={
            "avg_comfort_score": ":.2f",
            "selected": True,
            "temp" : True,
            "humidity" : True,
            "clear_slots": True,
            "rain_slots": True,
            "rain_sum": True,
            "wind_speed_max":True,
            "lat": False,
            "lon": False,
            "marker_size": False,
        },
        zoom=5,
        center={"lat": 46.6, "lon": 2.5},
        mapbox_style="open-street-map",
        color="avg_comfort_score",
        color_continuous_scale=px.colors.sequential.Jet,
        title="Top villes - indice de confort météo",
    )
    fig.update_layout(height=650, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def plot_city_hotels(cities_top20_hotels: pd.DataFrame, city: str):
    """Carte des hôtels pour une ville sélectionnée."""
    sub = cities_top20_hotels[cities_top20_hotels["city"] == city].copy()
    if sub.empty:
        return None

    lat_city = sub.iloc[0]["lat_city"]
    lon_city = sub.iloc[0]["lon_city"]
    checkin_date = sub.iloc[0].get("checkin_date", "")
    checkout_date = sub.iloc[0].get("checkout_date", "")

    sub["marker_hotel_size"] = (sub["combined_score_hotel"] > 0).map({True: 15, False: 5})

    fig = px.scatter_mapbox(
        sub,
        lat="lat_hotel",
        lon="lon_hotel",
        size="marker_hotel_size",
        size_max=20,
        hover_name="hotel_name",
        hover_data={
            "hotel_description": True,
            "url_hotel": True,
            "address_hotel": True,
            "score_hotel": ":.1f",
            "price_hotel": ":.2f",
            "lat_hotel": False,
            "lon_hotel": False,
            "marker_hotel_size": False,
        },
        zoom=10,
        center={"lat": lat_city, "lon": lon_city},
        mapbox_style="open-street-map",
        color="score_hotel",
        color_continuous_scale=px.colors.sequential.Jet,
        title=f"Hotels in {city} from {checkin_date} to {checkout_date}",
    )
    fig.update_layout(height=440, margin=dict(l=0, r=0, t=40, b=0))
    return fig

import pandas as pd
import streamlit as st


def afficher_hotels(hotels_df: pd.DataFrame | None, 
                    weather_df: pd.DataFrame | None = None) -> None:
    """Affiche le tableau des villes, meteo, hôtels 
    et avec le nom cliquable (lien vers l'hôtel).
    """
    
    
    if hotels_df is None or hotels_df.empty:
        st.info("La liste des hôtels apparaîtra ici après une recherche.")
        return

        nom_col, "city", "score_hotel", "price_hotel", "currency_hotel",
        nom_col, "city", "score_hotel", "price_hotel", "currency_hotel",
    df = hotels_df.copy().sort_values(by="combined_score_hotel",ascending=False)  # évite de modifier le DataFrame d'origine
    
    if weather_df is not None:
        df = df.merge(
            weather_df[["city","checkin_date","checkout_date","avg_comfort_score"]], 
            on=["city","checkin_date","checkout_date"], how="left")
        # let's take 2 best hotels by city by order of avg_comfort_score, 
        # then hotels by order of  combined_score_hotel
        
    else:
        df["avg_comfort_score"]= None

    df = df.sort_values(
            by=["avg_comfort_score","combined_score_hotel"],
            ascending=[False,False])
    # Colonne cliquable : "<url>#<nom>" -> la regex n'affichera que le nom
    if {"hotel_name", "url_hotel"} <= set(df.columns):
        nom = (
            df["hotel_name"].astype("string")
            .fillna("Hôtel")
            .str.replace("#", "", regex=False)  # '#' casserait la regex
            .str.strip()
        )
        url = df["url_hotel"].astype("string").str.strip()
        url_valide = url.notna() & url.str.startswith(("http://", "https://"), na=False)

        # Sans URL valide : on garde le nom seul (affiché en texte simple)
        df["hotel_link"] = nom.where(~url_valide, url + "#" + nom)
        nom_col = "hotel_link"
    else:
        nom_col = "hotel_name" if "hotel_name" in df.columns else None

    candidate_cols = [
        "city", "avg_comfort_score", nom_col, "combined_score_hotel", "score_hotel", "price_hotel",
    ]
    display_cols = [c for c in candidate_cols if c and c in df.columns]

    column_config = {}
    if nom_col == "hotel_link":
        column_config["hotel_link"] = st.column_config.LinkColumn(
            "Hôtel",
            display_text=r"#(.*)$",  # affiche le nom situé après le '#'
        )
    if "city" in display_cols:
        column_config["city"] = st.column_config.TextColumn("Ville")
    if "price_hotel" in display_cols:
        column_config["price_hotel"] = st.column_config.NumberColumn("Prix (€)", format="%.0f")
    if "score_hotel" in display_cols:
        column_config["score_hotel"] = st.column_config.NumberColumn("Note Booking", format="%.1f")
    if "currency_hotel" in display_cols:
        column_config["currency_hotel"] = st.column_config.TextColumn("Devise")
    if "avg_comfort_score" in display_cols:
        column_config["avg_comfort_score"] = st.column_config.TextColumn("Score météo")
    if "combined_score_hotel" in display_cols:
        column_config["combined_score_hotel"] = st.column_config.TextColumn("Note Glob")
    
    
    st.dataframe(
        df[display_cols],
        column_config=column_config,
        height=850,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# Chargement des données météo (mis en cache, ne recharge pas à chaque clic)
# ============================================================

# -- 28/09 
# @st.cache_data(ttl=3600, show_spinner="Chargement des prévisions météo...")
# def load_weather() -> pd.DataFrame:
#     try:
#         return get_weather_summary()
#     except Exception as e:
#         st.error(f"Erreur lors du chargement météo : {e}")
#         return pd.DataFrame(columns=["date", "city", "lat", "lon", "avg_comfort_score", "selected"])

# ++ 28/09 
if "hotels_df" not in st.session_state:
    st.session_state.hotels_df = None

try:
    keys = keys_from_df(load_search_keys())
    weather, cities = load_weather(), load_top_cities()
except Exception as e:  # ex. timeout RDS / security group
    st.error(f"Base de données inaccessible : {e}")
    st.stop()

# Dates proposées = dates des fenêtres précalculées (aujourd'hui et après)
today = date.today()
available_dates = sorted({d for k in keys for d in (k.checkin, k.checkout) if d >= today})

# Carte météo France : dernier run de la table weather + coordonnées des villes
top_cities = pd.DataFrame(columns=COLS_TOP_CITIES)  # recalculé après le sélecteur de dates
# if weather.empty:
#     top_cities = pd.DataFrame(columns=["city", "lat", "lon", "avg_comfort_score", "selected"])
# else:
#     latest = weather[weather["checkin_date"] == weather["checkin_date"].max()].drop_duplicates("city_id")
#     coords = cities.drop_duplicates("city_id")[["city_id", "city_lat", "city_lon"]]
#     top_cities = (
#         latest.merge(coords, on="city_id", how="left")
#          .dropna(subset=["lat", "lon"])
#          .drop(columns=['city_lat','city_lon'])
#     )
# end ++

# --
# if "hotels_df" not in st.session_state:
#     st.session_state.hotels_df = None

# result_weather = load_weather()

# # Villes/indice météo (top_cities) : dernière date par ville, ou agrégat moyen
# if not result_weather.empty:
#     top_cities = (
#         result_weather.groupby(["city", "lat", "lon"], as_index=False)["avg_comfort_score"]
#         .mean()
#     )
#     top_cities["selected"] = 0
# else:
#     top_cities = pd.DataFrame(columns=["city", "lat", "lon", "avg_comfort_score", "selected"])


# ============================================================
# BANDEAU DU HAUT (~1/5 de la hauteur)
# ============================================================

# Espace au-dessus du logo et du titre (padding haut de la page)
st.markdown(
    """
    <style>
        /* Zone principale : padding haut augmenté (défaut ≈ 6rem) */
        .block-container {
            padding-top: 0.25rem;
        }
        /* Décalage du titre pour l'aligner visuellement avec le logo */
        .kayak-title h2 {
            margin-top: 0.4rem;
            padding-top: 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container():
    # Espacement vertical supplémentaire au-dessus de la ligne logo/titre
    st.markdown("<div style='height: 0.25rem;'></div>", unsafe_allow_html=True)

    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        st.image(
            "https://seekvectorlogo.com/wp-content/uploads/2018/01/kayak-vector-logo.png",
            width=110,
        )
    with col_title:
        st.markdown(
            "<div class='kayak-title'><h2>Plan your trip from weather forecasts</h2></div>",
            unsafe_allow_html=True,
        )

    # ++ 28/09:
    col_weather, col_hotels = st.columns(2)

    # 1) Occupation d'abord : les pastilles 🟢/🟠 en dépendent
    with col_hotels:
        st.markdown("#### Hotels")
        h1, h2, h3 = st.columns(3)
        n_adults = h1.number_input("Adults", min_value=1, value=DEFAULT_OCCUPANCY["n_adults"], step=1)
        n_children = h2.number_input("Children", min_value=0, value=DEFAULT_OCCUPANCY["n_children"], step=1)
        n_rooms = h3.number_input("Rooms", min_value=1, value=DEFAULT_OCCUPANCY["n_rooms"], step=1)
    occupancy = {"n_adults": n_adults, "n_children": n_children, "n_rooms": n_rooms}

    # 2) Dates (colonne de gauche) avec statut
    with col_weather:
        st.markdown("#### Weather")
        if len(available_dates) < 2:
            st.warning("Aucune recherche précalculée : lance d'abord pipeline.py.")
            picked = None
        else:
            picked = render_date_picker(available_dates, occupancy, keys)
            
    # 2bis) Villes filtrées selon les dates choisies
    checkin = checkout = None
    if picked:
        checkin, checkout, _ = picked
    top_cities = build_top_cities(weather, cities, checkin, checkout)
    
    # 3) Message + bouton adaptés au statut (on revient dans la colonne de droite)
    with col_hotels:
        if picked:
            checkin, checkout, in_db = picked
            n_scraped = int(top_cities["selected"].sum()) if not top_cities.empty else 0
            action = render_search_action(in_db, n_cities=n_scraped)
            st.session_state.hotels_df = load_hotels_for(checkin, checkout, **occupancy)
            if action == "load":
                try:
                    st.session_state.hotels_df = load_hotels_for(checkin, checkout, **occupancy)
                except Exception as e:
                    st.error(f"Lecture des hôtels impossible : {e}")
            elif action == "search":
                st.info("Recherche live à implémenter (ENABLE_LIVE_SEARCH).")

st.divider()


# ============================================================
# CORPS PRINCIPAL 1 
# ============================================================
col_left, col_right = st.columns([2, 2])

with col_left:
    if not top_cities.empty:
        if checkin and checkout:
            st.caption(f"Prévisions du {checkin:%d/%m/%Y} au {checkout:%d/%m/%Y}")
        st.plotly_chart(
            plot_France_cities(top_cities),
            use_container_width=True,
            key=f"map_france_{checkin}_{checkout}",  # force le re-rendu au changement de dates
        )
    else:
        st.info("Aucune ville disponible pour ces dates.")
        
hotels_df = st.session_state.hotels_df
with col_right:
    st.markdown("#### Hotel list")
    afficher_hotels(hotels_df, weather)
st.divider()
# ============================================================
# CORPS PRINCIPAL 2 
# ============================================================
col_left2, col_right2 = st.columns([2, 2])
selected_city, hotels_df2 = None, None   
with col_left2:
    st.markdown("#### Zoom sur une ville")
    if hotels_df is not None and not hotels_df.empty and "city" in hotels_df.columns:
        cities_list = sorted(hotels_df["city"].dropna().unique())
        selected_city = st.selectbox("Choisir une ville", cities_list)
        hotels_df2 = hotels_df[hotels_df["city"]==selected_city]
        fig_city = plot_city_hotels(hotels_df, selected_city)
        if fig_city is not None:
            st.plotly_chart(fig_city, use_container_width=True)
        else:
            st.warning("Pas de données hôtels pour cette ville.")
    else:
        st.info("Lance une recherche d'hôtels pour afficher le détail par ville.")

with col_right2:
    st.markdown(f"#### Hotels à {selected_city}")
    afficher_hotels(hotels_df2)
        
 