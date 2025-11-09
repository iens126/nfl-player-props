#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import matplotlib.pyplot as plt
import pandas as pd
from core.data_loader import find_player, pass_def, run_def

def visualize_stat(player, stat_cat, defense):
    STAT_MAP = {
    'passing_yards': ('passing_yards', 'pass'),
    'passing_tds': ('passing_tds', 'pass'),
    'attempts': ('attempts', 'pass'),
    'completions': ('completions', 'pass'),
    'receiving_yards': ('passing_yards', 'pass'),  # yards gained through air
    'receiving_tds': ('passing_tds', 'pass'),
    'rushing_yards': ('rushing_yards', 'run'),
    'rushing_tds': ('rushing_tds', 'run'),
    'carries': ('carries', 'run')
    }
    
    stats_df = find_player(player)
    stats_df = stats_df.sort_values("week")
    
    means = stats_df.mean(numeric_only=True)
    stds = stats_df.std(numeric_only=True)
    
    x=stats_df['week']
    y=stats_df[stat_cat]
    z=means[stat_cat]
    s=stds[stat_cat]
    width = .35

    # Pick correct defensive column + func from map
    if stat_cat in STAT_MAP:
        def_stat, def_type = STAT_MAP[stat_cat]
        def_df = pass_def(defense) if def_type == 'pass' else run_def(defense)

        # Weeks to keep = every week appearing in either dataset
        full_weeks = sorted(set(stats_df['week']).union(set(def_df['week'])))

        combined = pd.DataFrame({'week': full_weeks}).set_index('week')

        # Align both datasets to full week list
        combined['player'] = stats_df.set_index('week')[stat_cat]
        combined['defense'] = def_df.set_index('week')[def_stat]

        # Extract aligned series (now equal length)
        y = combined['player']
        d = combined['defense']

        # Means that ignore missing/broadcast
        mean_val = y.mean(skipna=True)
        std_val = y.std(skipna=True)
        def_mean = d.mean(skipna=True)

        # x-axis for ALL weeks
        x = combined.index

    else:
        d = def_mean = None
    

    fig, ax = plt.subplots(figsize=(6.5,4))


    # Player bars (skip NaN)
    ax.bar(x - width/2, y.fillna(0), width,
           color=["#2f8fdd" if not pd.isna(v) else "#1e1e1e" for v in y],
           label=f"{player}")

    # Defense allowed bars (skip NaN)
    ax.bar(x + width/2, d.fillna(0), width,
           color=["#ef8a62" if not pd.isna(v) else "#1e1e1e" for v in d],
           alpha=0.9,
           label=f"{defense} Allowed")
    
    ax.set_ylabel(stat_cat)
    ax.set_xlabel('Week')
    ax.set_title(f"{stat_cat.replace('_',' ').title()} Comparison")
    ax.set_xticks(x)

    # Player mean + SD
    ax.axhline(y=mean_val, color="red", linestyle="--", label=f"{player} Avg {mean_val:.1f}")
    #ax.axhline(y=mean_val + std_val, color="blue", linestyle="dotted", alpha=0.7)
    #ax.axhline(y=mean_val - std_val, color="blue", linestyle="dotted", alpha=0.7)

    # Defense allowed average
    if def_mean is not None:
        ax.axhline(y=def_mean, color="green", linestyle="--", alpha=0.9,
                   label=f"{defense} Avg Allowed {def_mean:.1f}")
    
    ax.legend(loc='upper right')

    fig.tight_layout()
    
    return fig

