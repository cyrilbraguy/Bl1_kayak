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
SRC_DIR = BASE_DIR / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- Imports des fonctions métier existantes : À ADAPTER ---
# scrap_hotels(checkin, checkout, n_adults, n_children, n_rooms) -> DataFrame hôtels
# get_weather_summary() -> DataFrame colonnes [date, city, lat, lon, avg_comfort_score, selected]
try:
    from hotels import scrap_hotels           # noqa: E402
    from weather import get_weather_summary   # noqa: E402
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
    fig.update_layout(height=480, margin=dict(l=0, r=0, t=40, b=0))
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


# ============================================================
# Chargement des données météo (mis en cache, ne recharge pas à chaque clic)
# ============================================================

@st.cache_data(ttl=3600, show_spinner="Chargement des prévisions météo...")
def load_weather() -> pd.DataFrame:
    try:
        return get_weather_summary()
    except Exception as e:
        st.error(f"Erreur lors du chargement météo : {e}")
        return pd.DataFrame(columns=["date", "city", "lat", "lon", "avg_comfort_score", "selected"])


if "hotels_df" not in st.session_state:
    st.session_state.hotels_df = None

result_weather = load_weather()

# Villes/indice météo (top_cities) : dernière date par ville, ou agrégat moyen
if not result_weather.empty:
    top_cities = (
        result_weather.groupby(["city", "lat", "lon"], as_index=False)["avg_comfort_score"]
        .mean()
    )
    top_cities["selected"] = 0
else:
    top_cities = pd.DataFrame(columns=["city", "lat", "lon", "avg_comfort_score", "selected"])


# ============================================================
# BANDEAU DU HAUT (~1/5 de la hauteur)
# ============================================================
with st.container():
    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        st.image(
            "https://seekvectorlogo.com/wp-content/uploads/2018/01/kayak-vector-logo.png",
            width=110,
        )
    with col_title:
        st.markdown("## Plan your trip from weather forecasts")

    col_weather, col_hotels = st.columns(2)

    # ---- Bloc météo (gauche) ----
    with col_weather:
        st.markdown("#### Weather")

        if result_weather.empty:
            st.warning("Aucune prévision météo disponible.")
            checkin_date = checkout_date = None
        else:
            date_span = sorted(result_weather["date"].unique())
            available_dates = date_span[:5]  # aujourd'hui à J+4

            c1, c2 = st.columns(2)
            with c1:
                checkin_date = st.selectbox("Check-in", available_dates, index=0)
            with c2:
                checkout_options = [d for d in available_dates if d >= checkin_date]
                checkout_date = st.selectbox(
                    "Check-out", checkout_options, index=len(checkout_options) - 1
                )

    # ---- Bloc hotels (droite) ----
    with col_hotels:
        st.markdown("#### Hotels")
        h1, h2, h3 = st.columns(3)
        with h1:
            n_adults = st.number_input("Adults", min_value=1, value=2, step=1)
        with h2:
            n_children = st.number_input("Children", min_value=0, value=0, step=1)
        with h3:
            n_rooms = st.number_input("Rooms", min_value=1, value=1, step=1)

        search_clicked = st.button("🔍 Search", use_container_width=True)
        if search_clicked:
            if checkin_date is None:
                st.error("Aucune date de prévision disponible, recherche impossible.")
            elif checkin_date > checkout_date:
                st.error("La date de check-in doit précéder la date de check-out.")
            else:
                with st.spinner("Recherche des hôtels en cours..."):
                    try:
                        st.session_state.hotels_df = scrap_hotels(
                            checkin_date, checkout_date, n_adults, n_children, n_rooms
                        )
                        st.success(f"{len(st.session_state.hotels_df)} hôtels trouvés.")
                    except Exception as e:
                        st.error(f"Erreur lors de la recherche d'hôtels : {e}")

st.divider()


# ============================================================
# CORPS PRINCIPAL
# ============================================================
col_left, col_right = st.columns([3, 2])

with col_left:
    if not top_cities.empty:
        st.plotly_chart(plot_France_cities(top_cities), use_container_width=True)
    else:
        st.info("Aucune donnée météo chargée pour le moment.")

    st.markdown("#### Zoom sur une ville")
    hotels_df = st.session_state.hotels_df
    if hotels_df is not None and not hotels_df.empty and "city" in hotels_df.columns:
        cities_list = sorted(hotels_df["city"].dropna().unique())
        selected_city = st.selectbox("Choisir une ville", cities_list)
        fig_city = plot_city_hotels(hotels_df, selected_city)
        if fig_city is not None:
            st.plotly_chart(fig_city, use_container_width=True)
        else:
            st.warning("Pas de données hôtels pour cette ville.")
    else:
        st.info("Lance une recherche d'hôtels pour afficher le détail par ville.")

with col_right:
    st.markdown("#### Hotel list")
    if hotels_df is not None and not hotels_df.empty:
        candidate_cols = [
            "hotel_name", "city", "score_hotel", "price_hotel", "currency_hotel", "url_hotel",
        ]
        display_cols = [c for c in candidate_cols if c in hotels_df.columns]

        column_config = {}
        if "url_hotel" in display_cols:
            column_config["url_hotel"] = st.column_config.LinkColumn(
                "Lien", display_text="Voir l'hôtel"
            )
        if "price_hotel" in display_cols:
            column_config["price_hotel"] = st.column_config.NumberColumn(
                "Prix", format="%.0f"
            )
        if "score_hotel" in display_cols:
            column_config["score_hotel"] = st.column_config.NumberColumn(
                "Note", format="%.1f"
            )

        st.dataframe(
            hotels_df[display_cols],
            column_config=column_config,
            height=850,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("La liste des hôtels apparaîtra ici après une recherche.")
