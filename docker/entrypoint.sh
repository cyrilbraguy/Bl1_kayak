#!/bin/sh
set -e

# Ordonnanceur en arrière-plan (pipeline 2 fois par jour)
python /home/app/src/scheduler.py &

# Streamlit au premier plan (PID 1) : l'arrêt du conteneur coupe tout proprement
exec streamlit run /home/app/src/dashboard_app.py \
    --server.port="${PORT:-7860}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false