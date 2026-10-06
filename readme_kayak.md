
# Projet Kayak : 
![Kayak](https://seekvectorlogo.com/wp-content/uploads/2018/01/kayak-vector-logo.png)

# Pitch
This is a travel application, a search engine to identify the best trip destinations within a list of 35 cities to visit in France, from reliable informations on :
- weather, 
- hotel rooms availability in these destinations  
  
The application will propose you the best destinations and hotels based on the above criteria and time window 

## Application :  
### 1. Cities :  
 - The application uses a list of 35 cities recommendeded to visit in France according to <a href="https://one-week-in.com/35-cities-to-visit-in-france/" target="_blank">One Week In.com</a> 

 - Get the GPS coordinates from https://nominatim.org/
 - Dataframe of cities are stored in S3 volume with columns :
   | column | description  | 
   |--------|--------------|
   | city_name | city name with spaces |
   | city_name_ | city name with _ replacing spaces | 
   | city_plus | city name with _ replacing spaces | 
   | lat | latitude | 
   | lon | longitude |
   | city_lat |  | 
   | city_lon |  |   
   | city_id | unique id from city-name-lat-lon with resp. 4 and 3 digits |  
  
    
### 2. get weather data :  
- Weather data of all cities are extracted from https://openweathermap.org/ <a href="https://nominatim.org/release-docs/develop/api/Search/" target="_blank">free API</a> on the next 5 days thanks to a free_weather_API_key in json format, on 3 hours slots with several properties : 
visibility,	pop	main_temp,	main_feels_like,	main_temp_min,	main_temp_max,	main_pressure,	main_sea_level,	main_grnd_level,	main_humidity,	main_temp_kf,	main_dew_point,	clouds_all,	wind_speed,	wind_deg,	wind_gust,	sys_pod	rain_3h,	weather_id,	weather_main,	weather_description,	weather_icon,	datetime  

- Weather data are summarised on each day and a global comfort_score is computed :  
 #### Weather comfort score

A score from **0 to 1** (1 = ideal weather), computed for each city over the stay period.
It is a weighted average of 5 criteria, each scaled between 0 and 1.

| Weight | Criterion | Formula | Interpretation |
|-------:|-----------|---------|----------------|
| 30% | Clear sky | `clear_sky_ratio` | Share of forecast slots with a clear sky |
| 25% | Humidity | `1 − humidity / 100` | 0% → 1; 100% → 0 |
| 20% | Rain | `1 − pop_max` | `pop_max` = maximum probability of precipitation |
| 15% | Temperature | `1 − abs(T − 21) / 15` | Optimum at 21 °C; 0 at 6 °C or 36 °C |
| 10% | Wind | `1 − wind_max / 15` | 0 m/s → 1; 15 m/s (≈ 54 km/h) → 0 |

**Calculation**: each criterion is clipped to [0, 1], weighted and summed. The total is
then clipped and rounded to 2 decimals.

**Example**: clear sky 50%, humidity 60%, pop 0.2, 18 °C, max wind 6 m/s
→ 0.15 + 0.10 + 0.16 + 0.12 + 0.06 = **0.59**

#### Limitations
- Weights are chosen arbitrarily, not calibrated on data.
- Single temperature optimum (21 °C), the same for every type of trip.
- `pop_max` and max wind are pessimistic: one bad slot penalizes the whole period.
- Clear sky and humidity are correlated, so the "good weather" effect is partly counted twice.
- Assumed units: °C, m/s, rain probability between 0 and 1.

### Time windows 
Several time windows are computed on which comfort score can be computed 
### Best destinations 
Cities are ordered on this comfort_score from top to worste ,  
The 5 best destinations are selected  

- Dataframe of cities & weather data are stored in S3 volume with columns :
   | column | description  |  
   |--------|--------------|  
   | city | city name with spaces |  
   | avg_comfort_score | average comfort score |  
   | checkin_date | checkin date of time window |  
   | checkout_date | checkout date of time window |  
   | rain_sum | sum of rain volume in mm |  
   | temp | average temperature °C |  
   | humidity | average humidity in % |  
   | clear_slots | nb of clear sky slots of 3 hours on 9h - 18h |  
   | rain_slots | nb of rain slots of 3 hours on 9h - 18h  |  
   | wind_speed_max | max wind speed (km/h) |  
   | scraped_at | time stamp of weather scrap |  
   | selected| 1 if city is selected 0 if not |  
   | city_name_ | city name with _ replacing spaces |   
   | city_plus | city name with _ replacing spaces |  
   | city_lat | latitude |  
   | city_lon | longitude |    
   | city_id | unique id from city-name-lat-lon with resp. 4 and 3 digits |    
 

### 3. Get hotels for these 5 best destinations
These tasks are accomplished on each time window:
#### 3.1 Scrap booking.com 

From site booking.com, hotels are searched on time window and informations are collected into a dataframe. 
A function to scrap booking.com has been developped especially for that purpose.  As Booking.com is highly protected against these types of requests, pls use this solution with parcimony. 
This function is using playwright as pages are not compliant to beatifulsoup.   
Informations collected are at least : 

*   hotel name,
*   Url to its booking.com page,
*   Hotel adress, and city if not the one of the search 
*   Text description of the hotel
*   Its coordinates: latitude and longitude
*   Score given by the website users
*   price of the room (s)
*   Text description of the room

  
### 3.2 order hotels 

Hotels are then ordered with **combined_score** a combination of : 
* booking score
* penality if `price_hotel` is above a **max_price** fixed in the program (here for example at 300€)  
max_price = 300€ for example, 
 p = (10-0)/1   : as max score_hotel is 10 , so that any `price_hotel` above *max_price* will make a `combined_score` below *0* 
Combined_score = score_hotel - p * (price_hotel - max_price).clip(lower=0)  
   
A special order function could be designed that would select top best 2 hotels for each city by inverse order of best weather 

Hotels Results are merged with weather_cities table and stored in a CSV file in S3 bucket : 


columns :  
    | column | description  |  
    |--------|--------------|  
    | city | city name with spaces |  
    | avg_comfort_score | average comfort score |  
    | checkin_date | checkin date of time window |  
    | checkout_date | checkout date of time window |  
    | rain_sum | sum of rain volume in mm |  
    | temp | average temperature °C |  
    | humidity | average humidity in % |  
    | clear_slots | nb of clear sky slots of 3 hours on 9h - 18h |  
    | rain_slots | nb of rain slots of 3 hours on 9h - 18h  |  
    | wind_speed_max | max wind speed (km/h) |   
    | scraped_at | time stamp of weather scrap |  
    | selected| 1 if city is selected 0 if not |  
    | city_name_ | city name with _ replacing spaces |  
    | city_plus | city name with _ replacing spaces |  
    | city_lat | latitude |  
    | city_lon | longitude |    
    | city_id | unique id from city-name-lat-lon with resp. 4 and 3 digits |  

    
    | hotel_name | name of hotel |  
    | url_hotel | url of page |  
    | address_hotel | address of hotel |  
    | hotel_description | description of hotel |  
    | lat_hotel | latitude |  
    | lon_hotel | longitude |  
    | score_hotel | booking score |  
    | price_hotel | price of room(s) |  
    | currency_hotel | currency of hotel price |  
    | room_description | room description |  
    | hotel_city | city of hotel that could differ from city searched |  
    | combined_score_hotel | combined with max price as score_hotel - p * (price_hotel - max_price).clip(lower=0) ; p = (10-0)/1 |  
    | n_adults | default 2 |  
    | n_children | default 0 |  
    | n_rooms | default 1 |  



### Frontend streamlit 

A frontend streamlit is developped showing : 

### pipeline.py : 

To extract these data, a time of at least 5 minutes is necessary, so it has been decided to design a pipeline that would be launched 2 times a day and make ETL activity to properly store data in a SQL database :

3 tables are built to respect unicity of data principle : 
  | table | key_id | columns |
  |-------|--------|---------|
  | cities | city_id | city, city_id, city_lat, city_lon, city_name_, city_plus |
  | weather | city_id ; checkin_date ; checkout_date | city_id, city, checkin_date, checkout_date, avg_comfort_score, ... selected, lat, lon |
  | hotels | city_id ; checkin_date ; checkout_date | city_id, city, checkin_date, ... combined_score_hotel |

These tables are used by the fromtend for user consultation

# Application map 





#### updates in the pipe
- make work cron auto search !! 
- add buton w/ additional calc at new dates & options:
  update in_work in branch : manu_search
    - no modifier checkin a la premiere date doisponible dans weather // ?? 
    -  OK faire ajouter les dates manquantes
    - ok :ajouter/ param le bouton calculer
    - ok : cabler dessus le pipeline (params)
    - ok : update pipeline pour ajouter des tables ds la bd sql :
  
  search is operating and saves into db !! great 

  - to do remaining 06/10/26 : 
    - auto view hotels list when dates are selected on all configs even ones of auto search cron
    - when sel checkin date of manu search, auto update status of checkout, and auto update adults, children, .. of available lines !
    - check user_room_price used is compliant w/ daily limit 
    - after manu search, auto view & print result of this one ! 
    - make operate cities hotels print for a manu search ! 
  



# deployment 


Kayak_weather_hotels/  
├── src/                 (dashboard_app.py, pipeline.py, scheduler.py…)  
├── data/config/  
├── docker/              (Dockerfile, requirements.txt, entrypoint.sh)  
└── .dockerignore  

Kayak_weather_hotels/  
├── .dockerignore          ← ici  
├── src/  
├── data/config/  
└── docker/  
    ├── Dockerfile  
    ├── entrypoint.sh  
    └── requirements.txt  

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


# lancement du dockerfile : 
docker build -f docker/Dockerfile -t kayak_streamlit .

docker run --rm --name kayak -p 8501:8501 --shm-size=1g --env-file .env -e PIPELINE_HOURS=6,18 kayak_streamlit 

# pour lancer manuellement pipeline dans le docker en marche : 
docker run -d --name kayak -p 8501:8501 --shm-size=1g --env-file .env kayak_streamlit

# Lancer le pipeline à la demande, avec les logs en direct
docker exec -it -w /home/app/src kayak python pipeline.py


