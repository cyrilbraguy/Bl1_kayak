"""
date_picker.py
==============
Composants Streamlit pour le bandeau du dashboard :
  - render_date_picker  : check-in / check-out avec pastille 🟢 (en base) / 🟠 (nouvelle recherche)
  - render_search_action: message + bouton adaptés au statut, avec avertissement avant recherche lente

Streamlit ne sait pas colorer une option de selectbox : on utilise donc des pastilles emoji.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

import streamlit as st

import availability as av


def render_date_picker(
    available_dates: Iterable,
    occupancy: dict,
    keys: set[av.SearchKey],
    standard_checkout=None,
) -> tuple[date, date, bool] | None:
    """Affiche les 2 selectbox de dates. Retourne (checkin, checkout, in_db) ou None.

    - Pastille du check-in : calculée avec le check-out « standard » du pipeline (dernier jour).
    - Pastille du check-out : calculée avec le check-in actuellement choisi.
    """
    dates = sorted({av.to_date(d) for d in available_dates})
    if len(dates) < 2:
        st.warning("Il faut au moins 2 dates de prévision pour choisir un séjour.")
        return None

    std_checkout = av.to_date(standard_checkout) if standard_checkout else dates[-1]

    c1, c2 = st.columns(2)
    with c1:
        checkin = st.selectbox(
            "Check-in",
            dates[:-1],
            index=0,
            format_func=lambda d: av.label(d, av.make_key(d, std_checkout, **occupancy), keys),
        )
    with c2:
        checkout_options = [d for d in dates if d > checkin]
        checkout = st.selectbox(
            "Check-out",
            checkout_options,
            index=len(checkout_options) - 1,
            format_func=lambda d: av.label(d, av.make_key(checkin, d, **occupancy), keys),
        )

    st.caption(f"{av.EMOJI_IN_DB} déjà en base (instantané) · {av.EMOJI_NEW} nouvelle recherche (lente)")

    with st.expander("Voir toutes les combinaisons"):
        st.dataframe(av.availability_matrix(dates, occupancy, keys), use_container_width=True)

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
