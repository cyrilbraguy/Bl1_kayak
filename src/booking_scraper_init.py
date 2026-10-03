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


from os import name
import re
import json
import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional
from urllib.parse import urlencode
import unicodedata

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
SEL_ADDRESS = '[data-testid="address"]'
SEL_DESC_CANDIDATES = [
    '[data-testid="recommended-units"]',
    '[data-testid="property-card-unit-configuration"]',
]
SEL_PRICE_CANDIDATES = [
    '[data-testid="price-and-discounted-price"]',
    '[data-testid="price"]',
]


@dataclass
class Hotel:
    hotel_name: str
    url: str
    address: Optional[str]        # <-- ajouté
    hotel_description: Optional[str]  # <-- ajouté
    city: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    score: Optional[float]
    price: Optional[float]       # <-- ajouté
    currency: Optional[str]      # <-- ajouté
    room_description: Optional[str]

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "CHF": "CHF"}

def _parse_price(raw_text: str) -> tuple[Optional[float], Optional[str]]:
    """Extrait (montant, devise) d'un texte de prix Booking.com, ex. '€ 150'."""
    if not raw_text:
        return None, None
    currency = None
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in raw_text:
            currency = code
            break
    cleaned = raw_text.replace("\xa0", " ")
    m = re.search(r"[\d][\d\s.,]*\d|\d", cleaned)
    if not m:
        return None, currency
    number_str = m.group().replace(" ", "").replace(",", "")
    try:
        return float(number_str), currency
    except ValueError:
        return None, currency

def _guess_city_from_text(text: Optional[str]) -> Optional[str]:
    """Repli : cherche un motif 'CODE_POSTAL Ville' dans un texte d'adresse brut
    (utile quand l'adresse JSON-LD n'est pas structurée, ou pour le fallback DOM).
    Moins fiable que addressLocality mais capte souvent la bonne ville, y compris
    une ville voisine différente de la ville recherchée."""
    if not text:
        return None
    m = re.search(r"\b\d{4,6}\s+([A-Za-zÀ-ÖØ-öø-ÿ][\w'’\-\s]*?)(?:,|\s\d|$)", text)
    if m:
        city = m.group(1).strip()
        return city or None
    return None

def _norm(text: Optional[str]) -> str:
    """Minuscules, sans accents ni ponctuation : sert uniquement à comparer."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", t).strip()


def _contains(haystack: str, needle: Optional[str]) -> bool:
    """True si `needle` apparaît comme mot(s) entier(s) dans `haystack`."""
    n = _norm(needle)
    if not n:
        return True  # élément vide : rien à ajouter
    return re.search(rf"(?<!\w){re.escape(n)}(?!\w)", _norm(haystack)) is not None


def _build_address(street, postal, locality, country) -> Optional[str]:
    """Assemble l'adresse sans dupliquer ce que `street` contient déjà."""
    result = (street or "").strip().strip(",")
    ville = " ".join(p for p in (postal, locality) if p and not _contains(result, p))
    pays = country if country and not _contains(result, country) else None
    return ", ".join(p for p in (result, ville, pays) if p) or None


def _clean_address(text: Optional[str]) -> Optional[str]:
    """Nettoie une adresse brute : 1re ligne, segments identiques supprimés."""
    if not text:
        return None
    first_line = text.strip().splitlines()[0]
    seen, out = set(), []
    for seg in (s.strip() for s in first_line.split(",")):
        key = _norm(seg)
        if seg and key not in seen:
            seen.add(key)
            out.append(seg)
    return ", ".join(out) or None

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

async def _extract_property_details(context, hotel_url: str) -> dict:
    """Ouvre la page de l'hôtel et extrait latitude/longitude + hotel_description.
    JSON-LD (schema.org) en priorité, fallback data-atlas-latlng / meta hotel_description."""
    result = {"latitude": None, 
              "longitude": None, 
              "hotel_description": None,
              "address": None,
              "city": None,}
    page = None
    try:
        page = await context.new_page()
        await page.goto(hotel_url, timeout=20000, wait_until="domcontentloaded")

        for s in await page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(await s.inner_text())
                geo = data.get("geo") or {}
                if result["latitude"] is None and "latitude" in geo and "longitude" in geo:
                    result["latitude"] = float(geo["latitude"])
                    result["longitude"] = float(geo["longitude"])
                if result["hotel_description"] is None and data.get("description"):
                    result["hotel_description"] = str(data["description"]).strip()
                    
                addr = data.get("address")
                if result["address"] is None and isinstance(addr, dict):
                    street = addr.get("streetAddress")
                    postal = addr.get("postalCode")
                    locality = addr.get("addressLocality")
                    country = addr.get("addressCountry")
                    if isinstance(country, dict):
                        country = country.get("name")
                    # parts = [p for p in (street, " ".join(filter(None, [postal, locality])), country) if p]
                    # if parts:
                    #     result["address"] = ", ".join(parts)
                    # update get address 01/10/2026
                    result["address"] = _build_address(street, postal, locality, country)
                    if locality:
                        result["city"] = locality
                        
                elif result["address"] is None and isinstance(addr, str) and addr.strip():
                    # result["address"] = addr.strip()
                    result["address"] = _clean_address(addr)  
                    result["city"] = result["city"] or _guess_city_from_text(addr)   # <-- ligne ajoutée
                    
            except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
                continue

        if result["latitude"] is None:
            el = await page.query_selector("[data-atlas-latlng]")
            if el:
                latlng = await el.get_attribute("data-atlas-latlng")
                if latlng and "," in latlng:
                    lat, lng = latlng.split(",")
                    result["latitude"], result["longitude"] = float(lat), float(lng)

        if result["hotel_description"] is None:
            meta = await page.query_selector('meta[name="description"]')
            if meta:
                content = await meta.get_attribute("content")
                if content:
                    result["hotel_description"] = content.strip()
                    
        if result["address"] is None:
            for sel in ('[data-testid="PropertyHeaderAddressDesktop-wrapper"]', '[data-node_tt_id="header-address-link"]'):
                addr_el = await page.query_selector(sel)
                if addr_el:
                    text = (await addr_el.inner_text()).strip()
                    if text:
                        # result["address"] = text
                        result["address"] = _clean_address(text)
                                                
                        result["city"] = result["city"] or _guess_city_from_text(text)
                        # (supprime les 2 lignes "parts = ..." et l'ancien
                        #  result["city"] = result["city"] or (parts[-1] if parts else text))
                        
                    break
    except PWTimeout:
        logger.warning("Timeout détails : %s", hotel_url)
    except Exception as e:
        logger.warning("Erreur détails (%s) : %s", hotel_url, e)
    finally:
        if page:
            await page.close()
    return result


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
    fetch_description: bool = True,   # <-- ajouté
    fetch_address: bool = True,       # <-- ajouté
    headless: bool = True,
    navigation_timeout_ms: int = 30000,
) -> list[dict]:
    """
    Recherche les hôtels disponibles sur Booking.com pour les critères donnés.

    Retourne une liste de dicts (max `max_results`) avec les clés :
    hotel_name, url, latitude, longitude, score, room_description.

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

    search_city = city.strip()  # alias non masquable : conservé même si `city` est réutilisé plus bas
        
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
                hotel_name = (await name_el.inner_text()).strip() if name_el else None

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

                price = None
                currency = None
                for sel in SEL_PRICE_CANDIDATES:
                    price_el = await card.query_selector(sel)
                    if price_el:
                        raw_text = await price_el.inner_text()
                        price, currency = _parse_price(raw_text)
                        break

                
                room_description = None
                for sel in SEL_DESC_CANDIDATES:
                    desc_el = await card.query_selector(sel)
                    if desc_el:
                        room_description = (await desc_el.inner_text()).strip()
                        break
                
                address = None
                address_el = await card.query_selector(SEL_ADDRESS)
                if address_el:
                    address = (await address_el.inner_text()).strip()
                    # parts = [p.strip() for p in address.split(",") if p.strip()]
                    # city = parts[-1] if parts else address
                # Valeur de repli, utilisée seulement si l'extraction ci-dessous échoue
                # (ex. fetch_address=False ou page hôtel inaccessible). L'hôtel peut être
                # dans une ville voisine de search_city : ce n'est pas l'objectif final,
                # juste un filet de sécurité pour ne pas laisser city à None.
                city = search_city

                if not (hotel_name and hotel_url):
                    continue  # carte incomplète, on l'ignore plutôt que de planter

                lat, lng, hotel_description = (None, None, None)
                if fetch_coordinates or fetch_description or fetch_address:
                    details = await _extract_property_details(context, hotel_url)
                    if fetch_coordinates:
                        lat, lng = details["latitude"], details["longitude"]
                    if fetch_description:
                        hotel_description = details["hotel_description"]
                        
                    if fetch_address:
                        # La page détail (JSON-LD) est plus fiable que la carte de résultat ;
                        # on ne garde le repli carte que si la page détail n'a rien donné.
                        address = details["address"] or address
                        city = details["city"] or city
                
                
                # lat, lng = (None, None)
                # if fetch_coordinates:
                #     lat, lng = await _extract_latlng(context, hotel_url)

                #hotels.append(Hotel(hotel_name, hotel_url, lat, lng, score, room_description))
                #hotels.append(Hotel(hotel_name, hotel_url, lat, lng, score, price, currency, room_description))
                hotels.append(Hotel(hotel_name, hotel_url, address, hotel_description, 
                                    city, lat, lng, score, price, currency, room_description))
            except Exception as e:
                logger.warning("Erreur extraction d'une carte hôtel, carte ignorée : %s", e)
                continue

        await browser.close()

    return [asdict(h) for h in hotels]


def get_hotel_availability_sync(*args, **kwargs) -> list[dict]:
    """
    Wrapper synchrone, utilisable directement dans une cellule Jupyter sans `await`.

    Nécessaire sur Windows : le kernel Jupyter tourne sur un event loop
    (SelectorEventLoop) qui ne supporte pas la création de sous-processus,
    alors que Playwright doit lancer Chromium en sous-processus (seul
    ProactorEventLoop le permet). Comme on ne peut pas changer le type de
    loop d'un kernel déjà démarré, on exécute Playwright dans un thread
    séparé avec sa propre boucle correctement configurée.

    Usage :
        results = get_hotel_availability_sync(city="Lyon", 
            checkin_date="2026-11-10", checkout_date="2026-11-12")
    """
    import sys
    import threading

    print('ATTENTION : get_hotel_availability_sync() est un wrapper synchrone pour Jupyter/VSCode. Z')
    result_container: dict = {}
    error_container: dict = {}

    def runner():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_container["value"] = loop.run_until_complete(get_hotel_availability(*args, **kwargs))
        except Exception as e:
            error_container["error"] = e
        finally:
            loop.close()

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if "error" in error_container:
        raise error_container["error"]
    return result_container["value"]


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
