
Projet Kayak : 


Architecture du programme :: 
scrape_data.py :
read cities 

get coordinates 
save cities in S3 

--
get_weather.py :
    get weather 

    select_best_weather

---
get_hotels.py : 
    get_hotels 

    select_top_20_hotels 

    store final file in csv
---
ETL_data.py:
load_cities_weather_hotels.csv 

extract_cities & date of search
save cities in a cities_db w/ unique id ; 

extract hotels & date of search 
etl_selection 

store in db 






prompt pour le frontend streamlit : 

fabrique moi un dashboard streamlit qui va fonctionner avec mon main, avec dedans : 
a gauche:
 une carte qui affichera la meteo d'une liste de villes dont on a lat et lon et un critere 'beau temps' entre 0 et 1 ; selon le plot 'plot_meteo' utilisant plotly.express ci dessous 
a droite:
 une liste avec ascenseur qui affichera les hotels depuis la table , et une des colonnes comportera des hyperliens qui ouvriront un navigateur 

dans le bandeau du haut :
sur toute la largeur, le titre précédé du logo : Kayak   : [Kayak](https://seekvectorlogo.com/wp-content/uploads/2018/01/kayak-vector-logo.png) et le titre : "Plan your trip from weather forecasts"
 - a gauche : 
    un sous titre : weather
    les dates de début et de fin de la fenetre de prévision meteo sont celles de la variable date_span = result_weather["date"].unique() (de aujourdhui a j+5 (date_span[0] a date_span[4]))
    2 cases permettant de choisir les dates de début et de fin du trip (parmi les 5 jours possible de date_span : checkin , checkout )
 - A droite : 
   - un sous titre: hotels
  nb adults : default a 2
  nb children : def a 0
  nb rooms : def a 1
  un bouton "search" qui lance une fonction scrap_hotels avec checkin, checkout et les " var du dessus
 