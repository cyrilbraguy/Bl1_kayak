#FROM python:3.9-alpine
# FROM huanjason/scikit-learn
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=Europe/Paris \
    PORT=8501

WORKDIR /home/app

# Dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /tmp/requirements.txt \
 && playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright


# Utilisateur non-root (uid 1000, requis par Hugging Face Spaces)
RUN useradd -u 1000 -d /home/app app

COPY --chown=app:app src/ /home/app/src/
COPY --chown=app:app data/config/ /home/app/data/config/
COPY --chown=app:app docker/entrypoint.sh /home/app/entrypoint.sh

# sed : retire les fins de ligne Windows (CRLF) qui feraient échouer le script sous Linux
RUN sed -i 's/\r$//' /home/app/entrypoint.sh \
 && chmod +x /home/app/entrypoint.sh \
 && mkdir -p /home/app/data \
 && chown -R app:app /home/app

USER app
EXPOSE 8501
CMD ["/home/app/entrypoint.sh"]