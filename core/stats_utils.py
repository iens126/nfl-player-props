#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

bettable_columns = ['passing_yards','passing_tds','completions','attempts','passing_interceptions','targets','receptions','receiving_yards','receiving_tds','carries','rushing_yards','rushing_tds']

# Coefficient-of-variation thresholds used to bucket a stat's stability into a
# human-readable rating. Lower CV = less relative week-to-week swing = more stable.
STABILITY_THRESHOLDS = {'HIGH': 0.35, 'MEDIUM': 0.65}  # cv < HIGH -> "HIGH", < MEDIUM -> "MEDIUM", else "LOW"


def stability_rating(cv):
    """Bucket a coefficient of variation into HIGH / MEDIUM / LOW stability."""
    if cv is None or pd.isna(cv):
        return None
    if cv < STABILITY_THRESHOLDS['HIGH']:
        return 'HIGH'
    if cv < STABILITY_THRESHOLDS['MEDIUM']:
        return 'MEDIUM'
    return 'LOW'


def remove_outliers(df, cols=None, z_thresh=2.5):
    """
    Remove games that are statistical outliers for a player.
    Outliers are defined as rows where any of the specified columns
    have a z-score > z_thresh or < -z_thresh.
    """
    if cols is None:
        cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        # Keep only columns that exist in df
        cols = [c for c in cols if c in df.columns]

    z_scores = (df[cols] - df[cols].mean()) / df[cols].std(ddof=0)
    mask = (np.abs(z_scores) < z_thresh).all(axis=1)
    cleaned_df = df[mask].copy()

    # With a handful of games the standard deviation can be zero, which makes
    # every z-score NaN and drops the whole frame - and "this player has no
    # games" is never the right answer to "which of their games were unusual".
    # Callers downstream index into the result, so an empty frame surfaced as a
    # 500 on the player summary endpoint for anyone with very few appearances.
    if cleaned_df.empty:
        logger.debug("Outlier filter would empty %s; keeping all games", len(df))
        return df.copy()

    removed = len(df) - len(cleaned_df)
    if removed > 0:
        logger.debug("Removed %d outlier game(s) for %s", removed, df['player_display_name'].iloc[0])
    return cleaned_df

def determine_stability(df):
    if df.empty:
        raise ValueError("Cannot compute stability without any games")

    df = df.drop(columns = 'week')
    df = remove_outliers(df,
                        cols=bettable_columns,
                        z_thresh=2.5)
    names = df['player_display_name'].unique()
    player_name = names[0] if len(names) else None
    # Prop stats only: the game rows also carry numeric bookkeeping (season)
    # that has a mean and a spread but no stability to speak of.
    stat_cols = [c for c in bettable_columns if c in df.columns]
    means = df[stat_cols].mean(numeric_only=True)
    stds = df[stat_cols].std(numeric_only=True)
    # CV only means "relative swing" when the average is positive. A mean of
    # exactly zero gives infinity, which json.dumps writes as a bare `Infinity`
    # that the browser's JSON.parse rejects - that made Matthew Stafford's
    # whole player file unloadable. A negative mean (kneel-down rushing yards)
    # gives a negative CV, which the thresholds read as HIGH stability. Neither
    # is a stability reading, so those stats are dropped like 0/0 already was.
    cv = stds / means.where(means > 0)

    summary = pd.DataFrame({'mean':means,'std':stds,'cv':cv}).dropna()
    summary = summary.sort_values('cv', ascending=True)

    return player_name, summary

