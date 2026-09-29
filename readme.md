
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

 

