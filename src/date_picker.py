"""
date_picker.py
==============
Composants Streamlit pour le bandeau du dashboard :
  - render_date_picker  : check-in / check-out avec pastille 🟢 (en base) / 🟠 (nouvelle recherche)
  - render_search_action: message + bouton adaptés au statut, avec avertissement avant recherche lente

Streamlit ne sait pas colorer une option de selectbox : on utilise donc des pastilles emoji.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd
import streamlit as st

import availability as av


def full_date_range(start, end) -> list[date]:
    """Tous les jours entre start et end inclus."""
    s, e = av.to_date(start), av.to_date(end)
    if e < s:
        raise ValueError(f"Plage invalide : {s} > {e}")
    return [s + timedelta(days=i) for i in range((e - s).days + 1)]


def weather_dates_from_df(
    weather: pd.DataFrame,
    cols: tuple[str, ...] = ("checkin_date", "checkout_date", "date"),
) -> list[date]:
    """Dates présentes dans la table weather (colonnes de dates trouvées, doublons retirés)."""
    if weather is None or weather.empty:
        return []
    cols_ok = [c for c in cols if c in weather.columns]
    if not cols_ok:
        return []
    vals = pd.concat([weather[c] for c in cols_ok]).dropna()
    return sorted({av.to_date(v) for v in vals})


def render_date_picker(
    available_dates: Iterable,
    occupancy: dict,
    keys: set[av.SearchKey],
    standard_checkout=None,
    weather_dates: Iterable | None = None,
    min_date=None,
) -> tuple[date, date, bool] | None:
    """Affiche les 2 selectbox de dates. Retourne (checkin, checkout, in_db) ou None.

    - Dates proposées : TOUS les jours entre la première et la dernière date de `weather_dates`
      (à défaut, de `available_dates`), même sans recherche précalculée.
    - Pastille du check-in : 🟢 s'il existe une recherche précalculée commençant ce jour-là.
    - Pastille du check-out : calculée avec le check-in actuellement choisi.
    - `min_date` : ignore les dates antérieures (ex. aujourd'hui).
    """
    sources = [av.to_date(d) for d in (weather_dates or [])] or [av.to_date(d) for d in available_dates]
    if len(sources) < 2:
        st.warning("Il faut au moins 2 dates de prévision pour choisir un séjour.")
        return None

    dates = full_date_range(min(sources), max(sources))
    if min_date is not None:
        dates = [d for d in dates if d >= av.to_date(min_date)]
    if len(dates) < 2:
        st.warning("Il faut au moins 2 dates de prévision pour choisir un séjour.")
        return None

    std_checkout = av.to_date(standard_checkout) if standard_checkout else dates[-1]

    # Check-ins pour lesquels une recherche existe déjà, avec la même occupation
    occ = (int(occupancy["n_adults"]), int(occupancy["n_children"]), int(occupancy["n_rooms"]))
    checkins_en_base = {k.checkin for k in keys if (k.n_adults, k.n_children, k.n_rooms) == occ}

    # Nettoyage de l'état : une valeur qui n'est plus proposée est oubliée avant le widget
    checkin_options = dates[:-1]
    if st.session_state.get("dp_checkin") not in checkin_options:
        st.session_state.pop("dp_checkin", None)

    c1, c2 = st.columns(2)
    with c1:
        checkin = st.selectbox(
            "Check-in",
            checkin_options,
            index=0,
            key="dp_checkin",
            format_func=lambda d: f"{av.EMOJI_IN_DB if d in checkins_en_base else av.EMOJI_NEW} {d:%d/%m}",
        )

    checkout_options = [d for d in dates if d > checkin]
    if st.session_state.get("dp_checkout") not in checkout_options:
        st.session_state.pop("dp_checkout", None)
    # Par défaut : le check-out standard du pipeline s'il est valide, sinon le dernier jour
    default_co = std_checkout if std_checkout in checkout_options else checkout_options[-1]

    with c2:
        checkout = st.selectbox(
            "Check-out",
            checkout_options,
            index=checkout_options.index(default_co),
            key="dp_checkout",
            format_func=lambda d: av.label(d, av.make_key(checkin, d, **occupancy), keys),
        )

    st.caption(f"{av.EMOJI_IN_DB} déjà en base (instantané) · {av.EMOJI_NEW} nouvelle recherche (lente)")

    if len(dates) <= 12:
        with st.expander("Voir toutes les combinaisons"):
            st.dataframe(av.availability_matrix(dates, occupancy, keys), width="stretch")

    key = av.make_key(checkin, checkout, **occupancy)
    return checkin, checkout, av.is_in_db(key, keys)


def render_search_action(
    in_db: bool,
    n_cities: int,
    live_enabled: bool = av.ENABLE_LIVE_SEARCH,
) -> str:
    """Affiche le message et le bouton adaptés. Retourne "load" | "search" | "none".

    "load"   -> le dashboard lit les résultats déjà en base.
    "search" -> le dashboard lance la recherche live (à implémenter, protégée par confirmation).
    """
    if in_db:
        st.success(f"{av.EMOJI_IN_DB} Résultats disponibles en base : affichage instantané.")
        return "load" if st.button("🔍 Afficher", use_container_width=True) else "none"

    if not live_enabled:
        st.info(
            f"{av.EMOJI_NEW} Combinaison non précalculée. "
            "La recherche à la demande n'est pas encore activée : choisis une date 🟢."
        )
        return "none"

    minutes = av.estimate_search_minutes(n_cities)
    st.warning(
        f"{av.EMOJI_NEW} **Nouvelle recherche en direct** : environ {minutes:.0f} min. "
        "Elle interroge Booking pour chaque ville et ne peut pas être interrompue proprement."
    )
    confirmed = st.checkbox("J'ai compris, lancer quand même", key="confirm_live_search")
    clicked = st.button("🔍 Lancer la recherche", disabled=not confirmed, use_container_width=True)
    return "search" if clicked else "none"
