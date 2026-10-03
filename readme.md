
Projet Kayak : 

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


