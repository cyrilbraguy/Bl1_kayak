"""
Recherche de disponibilités d'hôtels sur Booking.com (API ASYNC)

AVERTISSEMENT :
- Le scraping de Booking.com est contraire à leurs Conditions d'Utilisation
  et le site déploie une protection anti-bot active (détection JS, rate-limiting,
  CAPTCHA). Ce code est fourni à titre éducatif / usage personnel modéré.
  Pour un usage en production, privilégier une API officielle (Booking.com
  Demand API partenaire, ou agrégateurs légaux type RapidAPI "Booking",
  Amadeus, etc.).
- Le site étant très dynamique (JS-heavy), Playwright est utilisé plutôt que
  requests/BeautifulSoup (le HTML brut ne contient pas les résultats).
- Version ASYNC (async_playwright) : nécessaire dans un notebook Jupyter/VSCode,
  qui tourne déjà dans une boucle asyncio (l'API sync de Playwright y échoue
  avec "Sync API inside the asyncio loop"). Utilisable aussi dans un script
  classique via asyncio.run(...).
- Les sélecteurs CSS/data-testid ci-dessous correspondent à la structure du
  site à date de rédaction et peuvent casser si Booking.com change son DOM.
  Ils sont isolés en haut du fichier pour être facilement mis à jour.

Installation :
    pip install playwright
    playwright install chromium

Usage dans un notebook :
    results = await get_hotel_availability(city="Lyon", checkin_date="2026-11-10", checkout_date="2026-11-12")

Usage dans un script .py classique :
    import asyncio
    results = asyncio.run(get_hotel_availability(city="Lyon", checkin_date="2026-11-10", checkout_date="2026-11-12"))
"""

import re
import json
import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Sélecteurs centralisés (à ajuster si Booking.com change sa structure) ---
SEL_COOKIE_BUTTONS = [
    'button[id="onetrust-accept-btn-handler"]',
    'button[aria-label="Dismiss sign-in info."]',
]
SEL_CARD = '[data-testid="property-card"]'
SEL_NAME = '[data-testid="title"]'
SEL_LINK = 'a[data-testid="title-link"]'
SEL_SCORE = '[data-testid="review-score"] div'
SEL_DESC_CANDIDATES = [
    '[data-testid="recommended-units"]',
    '[data-testid="property-card-unit-configuration"]',
]


@dataclass
class Hotel:
    name: str
    url: str
    latitude: Optional[float]
    longitude: Optional[float]
    score: Optional[float]
    description: Optional[str]


def _build_search_url(city: str, checkin: str, checkout: str, adults: int, rooms: int, children: int) -> str:
    params = {
        "ss": city,
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": adults,
        "no_rooms": rooms,
        "group_children": children,
        "selected_currency": "EUR",
    }
    return "https://www.booking.com/searchresults.html?" + urlencode(params)


async def _extract_latlng(context, hotel_url: str) -> tuple[Optional[float], Optional[float]]:
    """Ouvre la page de l'hôtel dans un nouvel onglet et tente d'en extraire lat/lng
    (attribut data-atlas-latlng, ou fallback JSON-LD schema.org)."""
    page = None
    try:
        page = await context.new_page()
        await page.goto(hotel_url, timeout=20000, wait_until="domcontentloaded")

        el = await page.query_selector("[data-atlas-latlng]")
        if el:
            latlng = await el.get_attribute("data-atlas-latlng")
            if latlng and "," in latlng:
                lat, lng = latlng.split(",")
                return float(lat), float(lng)

        for s in await page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(await s.inner_text())
                geo = data.get("geo") or {}
                if "latitude" in geo and "longitude" in geo:
                    return float(geo["latitude"]), float(geo["longitude"])
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
    except PWTimeout:
        logger.warning("Timeout coordonnées : %s", hotel_url)
    except Exception as e:
        logger.warning("Erreur coordonnées (%s) : %s", hotel_url, e)
    finally:
        if page:
            await page.close()
    return None, None


async def get_hotel_availability(
    city: str,
    checkin_date: str,          # format "YYYY-MM-DD"
    checkout_date: str,         # format "YYYY-MM-DD"
    group_adults: int = 2,
    no_rooms: int = 1,
    group_children: int = 0,
    max_results: int = 10,
    fetch_coordinates: bool = True,
    headless: bool = True,
    navigation_timeout_ms: int = 30000,
) -> list[dict]:
    """
    Recherche les hôtels disponibles sur Booking.com pour les critères donnés.

    Retourne une liste de dicts (max `max_results`) avec les clés :
    name, url, latitude, longitude, score, description.

    Lève ValueError si les dates sont invalides, RuntimeError en cas d'échec
    de chargement/absence de résultats.
    """
    try:
        d_in = date.fromisoformat(checkin_date)
        d_out = date.fromisoformat(checkout_date)
    except ValueError as e:
        raise ValueError(f"Format de date invalide (attendu YYYY-MM-DD) : {e}")
    if d_out <= d_in:
        raise ValueError("checkout_date doit être postérieure à checkin_date")
    if group_adults < 1 or no_rooms < 1 or group_children < 0:
        raise ValueError("group_adults/no_rooms doivent être >= 1, group_children >= 0")

    url = _build_search_url(city, checkin_date, checkout_date, group_adults, no_rooms, group_children)
    hotels: list[Hotel] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        page = await context.new_page()

        try:
            await page.goto(url, timeout=navigation_timeout_ms, wait_until="domcontentloaded")
        except PWTimeout:
            await browser.close()
            raise RuntimeError("Timeout lors du chargement de la page de recherche")

        # Fermer bandeaux cookies/login s'ils apparaissent
        for selector in SEL_COOKIE_BUTTONS:
            try:
                await page.click(selector, timeout=3000)
            except PWTimeout:
                pass

        try:
            await page.wait_for_selector(SEL_CARD, timeout=20000)
        except PWTimeout:
            await browser.close()
            raise RuntimeError(
                "Aucun résultat trouvé ou structure de page inattendue "
                "(sélecteurs probablement à mettre à jour)"
            )

        # Scroll pour déclencher le lazy-loading jusqu'à avoir assez de cartes
        cards = await page.query_selector_all(SEL_CARD)
        attempts = 0
        while len(cards) < max_results and attempts < 6:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1200)
            cards = await page.query_selector_all(SEL_CARD)
            attempts += 1

        for card in cards[:max_results]:
            try:
                name_el = await card.query_selector(SEL_NAME)
                name = (await name_el.inner_text()).strip() if name_el else None

                link_el = await card.query_selector(SEL_LINK) or await card.query_selector("a")
                hotel_url = await link_el.get_attribute("href") if link_el else None
                if hotel_url and hotel_url.startswith("/"):
                    hotel_url = "https://www.booking.com" + hotel_url
                elif hotel_url:
                    hotel_url = hotel_url.split("?")[0]  # nettoie les paramètres de tracking

                score = None
                score_el = await card.query_selector(SEL_SCORE)
                if score_el:
                    m = re.search(r"[\d.,]+", await score_el.inner_text())
                    if m:
                        score = float(m.group().replace(",", "."))

                description = None
                for sel in SEL_DESC_CANDIDATES:
                    desc_el = await card.query_selector(sel)
                    if desc_el:
                        description = (await desc_el.inner_text()).strip()
                        break

                if not (name and hotel_url):
                    continue  # carte incomplète, on l'ignore plutôt que de planter

                lat, lng = (None, None)
                if fetch_coordinates:
                    lat, lng = await _extract_latlng(context, hotel_url)

                hotels.append(Hotel(name, hotel_url, lat, lng, score, description))
            except Exception as e:
                logger.warning("Erreur extraction d'une carte hôtel, carte ignorée : %s", e)
                continue

        await browser.close()

    return [asdict(h) for h in hotels]


async def _demo():
    results = await get_hotel_availability(
        city="Lyon",
        checkin_date="2026-11-10",
        checkout_date="2026-11-12",
        group_adults=2,
        no_rooms=1,
        max_results=10,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_demo())
