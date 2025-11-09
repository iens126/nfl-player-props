#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import numpy as np
import pandas as pd

bettable_columns = ['passing_yards','passing_tds','completions','attempts','passing_interceptions','targets','receptions','receiving_yards','receiving_tds','carries','rushing_yards','rushing_tds']

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
    
    removed = len(df) - len(cleaned_df)
    if removed > 0:
        print(f"Removed {removed} outlier game(s) for {df['player_display_name'].iloc[0]}")
    return cleaned_df

def determine_stability(df):
    df = df.drop(columns = 'week')
    df = remove_outliers(df, 
                        cols=bettable_columns,
                        z_thresh=2.5)
    player_name = df['player_display_name'].unique()[0]
    means = df.mean(numeric_only=True)
    stds = df.std(numeric_only=True)
    cv = stds/means

    summary = pd.DataFrame({'mean':means,'std':stds,'cv':cv}).dropna()
    summary = summary.sort_values('cv', ascending=True)
    
    return player_name, summary

