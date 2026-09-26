# ====================================================================
# Kayak project Cyril 
# module 6 : 
# config_kayak.py 
# (c) 2026-09-20 
# ====================================================================

import plotly.express as px
import pandas as pd

def plot_France_cities(top_cities):
    
    import plotly.express as px
    # plot all cities wiith their average comfort score on a map of France
    top_cities["marker_size"] = top_cities['selected'].map({1:15, 0:5})  # Example sizes for selected and non-selected cities
    fig = px.scatter_mapbox(top_cities, 
                        lat="lat", 
                        lon="lon",
                        size="marker_size", 
                        size_max = 20,
                        hover_name="city", 
                        hover_data={"avg_comfort_score": ":.2f", "selected": True, "lat": False, "lon": False, "marker_size": False},
                        zoom=5,
                        center={"lat": 46.6, "lon": 2.5},
                        mapbox_style="open-street-map",
                        color="avg_comfort_score", 
                        color_continuous_scale=px.colors.sequential.Jet, 
                        #color_continuous_scale=px.colors.sequential.bluered, 
                        title="Top 7 Cities with Best Weather Conditions in France")
    date_heure_today = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    fig.update_layout(title=f"Indice de confort météo par ville; prévisions du {date_heure_today}", 
                    width = 900,
                    height=700,
                    margin=dict(l=0, r=0, t=40, b=0))
    fig.show()
        

def plot_city_hotels(cities_top20_hotels_2,city):
    """plot a map of a city selected with hotels location on it 
    and some informations 

    Args:
        cities_top20_hotels_2 (_type_): _description_
        city (_type_): _description_
    """
    cities_top20_hotels_sub = cities_top20_hotels_2[cities_top20_hotels_2["city"]==city]
    
    
    lat_city = cities_top20_hotels_sub.iloc[1]["lat_city"]
    lon_city = cities_top20_hotels_sub.iloc[1]["lon_city"]
    checkin_date = cities_top20_hotels_sub.iloc[1]["checkin_date"]
    checkout_date = cities_top20_hotels_sub.iloc[1]["checkout_date"]
    
    # plot all cities wiith their average comfort score on a map of France
    cities_top20_hotels_sub["marker_hotel_size"] = (
        cities_top20_hotels_sub['combined_score_hotel']>0).map({True:15, False:5})  # Example sizes for selected and non-selected cities
    fig = px.scatter_mapbox(cities_top20_hotels_sub, 
                        lat="lat_hotel", 
                        lon="lon_hotel",
                        size="marker_hotel_size", 
                        size_max = 20,
                        hover_name="hotel_name", 
                        hover_data={"hotel_description":True , "url_hotel" :True , "address_hotel":True,
                                    "score_hotel": ":.1f", "price_hotel": ":.2f", 
                                    "lat_hotel":False, "lon_hotel":False,"marker_hotel_size":False},
                        zoom=10,
                        center={"lat": lat_city, "lon": lon_city},
                        mapbox_style="open-street-map",
                        color="score_hotel", 
                        color_continuous_scale=px.colors.sequential.Jet, 
                        #color_continuous_scale=px.colors.sequential.bluered, 
                        title=f"Hotels in {city} from {checkin_date} to {checkout_date}")
    date_heure_today = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    fig.update_layout(title=f"Hotels in {city} from {checkin_date} to {checkout_date}", 
                    width = 900,
                    height=700,
                    margin=dict(l=0, r=0, t=40, b=0))
    fig.show()