#!/usr/bin/env python
# coding: utf-8

# In[6]:


# Import necessary packages.
from core.data_loader import *
from core.stats_utils import *
import matplotlib.pyplot as plt
from rapidfuzz import process, fuzz
import statistics
#_______________________________________________________________________________________________________________________

DEBUG = True

# Create function to get league average allowed of a specific stat category. To be used later in weighting predictions.
def def_league_stats(stat_cat):
    team_stats = load_team_data()
    avg = team_stats[stat_cat].mean()
    std = team_stats[stat_cat].std()
    return avg, std
#_______________________________________________________________________________________________________________________

# Create function that requires a fuzzy string similarity.
def best_name_match(name, name_list, threshold=85):
    match, score, _ = process.extractOne(name, name_list, scorer=fuzz.token_sort_ratio)
    if score >= threshold:
        return match
    else:
        return None
#_______________________________________________________________________________________________________________________

# Create function to get a players rank in the depth chart. Will help in identifying a defenses yards allowed to a specific position rank.
def get_pos_rank(name):
    depth = load_depth_data()
    player_stats = load_player_data()
    pos = player_stats[player_stats['player_display_name'] == name]['position'].unique()[0]
    depth_names = depth[depth['pos_abb'] == pos]['player_name'].unique()
    match = best_name_match(name, depth_names)

    if match is None:
        return np.nan
    
    rank = depth[(depth['player_name'] == match) & (depth['pos_abb'] == pos)]['pos_rank'].iloc[0]
    return rank
#_______________________________________________________________________________________________________________________

# Create a function that divides up players in a certain position into depth chart rank to obtain a defenses average vs a rank of a position group.
# Applicable primarily for RB and WR i.e. multiple WR's will make catches.
# Acts as a way to mimic CB matchups with a WR.
def by_positon_rank(defense, pos, stat_cat):
    player_stats = load_player_data()
    if defense == 'NFL':
        positional_stats = player_stats[player_stats['position'] == pos].copy()
    else:
        positional_stats = player_stats[(player_stats['opponent_team'] == defense) & (player_stats['position'] == pos)].copy()

    positional_stats['rank'] = positional_stats['player_display_name'].map(
        {p: get_pos_rank(p) for p in positional_stats['player_display_name'].unique()})

    positional_stats['rank_group'] = positional_stats['rank'].apply(
        lambda r: r if r in [1, 2, 3] else 'other'
    )

    stats = (positional_stats.groupby('rank_group')[stat_cat].agg(['mean', 'std', 'count']).reset_index())

    for group in [1, 2, 3, 'other']:
        if group not in stats['rank_group'].values:
            stats.loc[len(stats)] = [group, np.nan, np.nan, 0]

    return stats
#_______________________________________________________________________________________________________________________

# Create function that creates a defensive strength index to be used in the creation of weights
def pass_def_index(team_stats):
    df = team_stats.copy()

    df['def_team'] = df['opponent_team']

    for col in ['passing_yards', 'attempts','passing_tds','passing_interceptions','sacks_suffered']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    agg = df.groupby('def_team').agg(passing_yards = ('passing_yards','mean'),
                                     attempts = ('attempts','mean'),
                                     passing_tds = ('passing_tds','mean'),
                                     passing_interceptions = ('passing_interceptions','mean'),
                                     sacks_suffered = ('sacks_suffered', 'mean')).reset_index()

    if DEBUG:
        missing = df['opponent_team'].isna().sum()
        print(f'[DEBUG] pass_def_index(): Built {len(agg)} teams, missing opponent_team in {missing} rows')
    
    agg['yards_per_att'] = safe_divide(agg['passing_yards'],agg['attempts'])
    agg['td_rate'] = safe_divide(agg['passing_tds'],agg['attempts'])
    agg['int_rate'] = safe_divide(agg['passing_interceptions'],['attempts'])
    agg['sack_rate'] = safe_divide(agg['sacks_suffered'],agg['sacks_suffered']+agg['attempts'])

    for col in ['passing_yards','yards_per_att','td_rate','int_rate','sack_rate']:
        agg[col+'_z'] = (agg[col] - agg[col].mean(skipna=True))/agg[col].std(skipna=True, ddof=0)

    agg['dsi'] = (-0.4 * agg['passing_yards_z']
                  -0.4 * agg['yards_per_att_z']
                  -0.2 * agg['td_rate_z']
                  +0.3 * agg['int_rate_z']
                  +0.3 * agg['sack_rate_z'])

    agg['dsi'] = (agg['dsi'] - agg['dsi'].mean(skipna=True))/agg['dsi'].std(skipna=True,ddof=0)
    
    return agg[['def_team', 'dsi']]

# Create function that makes the weight based on the players standard deviation, and defenses Z score (using league-wide average
# and standard deviation to calculate.
def create_weight(name, def_team, stat_cat, def_index_df, k = 0.6):
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
    pos = find_player(name)['position'].unique()[0]

    if pos == 'QB':
        zdef = float(def_index_df.loc[def_index_df['def_team'] == def_team, 'dsi'])
        player_std = find_player(name)[stat_cat].std()
        league_avg = def_league_stats(stat_cat)[0]
        league_std = def_league_stats(stat_cat)[1]
        if STAT_MAP[stat_cat][1] == 'pass':
            team_avg = pass_def(def_team)[stat_cat].mean()
        elif STAT_MAP[stat_cat][1] == 'run':
            team_avg = run_def(def_team)[stat_cat].mean()

        #zdef = (team_avg - league_avg)/ league_std
    
        weight = k * player_std * (-zdef)

    else:
        k = .3
        player_std = find_player(name)[stat_cat].std()
        rank = get_pos_rank(name)
        if rank == 1:
            league_avg = by_positon_rank('NFL', pos, stat_cat).iat[0,1]
            defense_avg = by_positon_rank(def_team, pos, stat_cat).iat[0,1]
        elif rank == 2:
            league_avg = by_positon_rank('NFL', pos, stat_cat).iat[1,1]
            defense_avg = by_positon_rank(def_team, pos, stat_cat).iat[1,1]
        elif rank == 3:
            league_avg = by_positon_rank('NFL', pos, stat_cat).iat[2,1]
            defense_avg = by_positon_rank(def_team, pos, stat_cat).iat[2,1]
        else:
            league_avg = by_positon_rank('NFL', pos, stat_cat).iat[3,1]
            defense_avg = by_positon_rank(def_team, pos, stat_cat).iat[3,1]
        
        weight = k * (defense_avg - league_avg)

    if np.isnan(weight) or np.isinf(weight):
        if DEBUG:
            print(f'[DEBUG] NaN/Inf weight for {name} vs {def_team}: zdef={zdef}, player_std={player_std}')
    
    return weight
#_______________________________________________________________________________________________________________________

# Create function that runs simulations of the players stats for a specified category and calculates the probability that
# the player gets over a specific line of the stat.
def run_sim(name, def_team, stat_cat, line):
    results = []
    n_simulations = 10000
    df = find_player(name)
    values = df[stat_cat]
    #values = values.round(-1)
    a = values.min()
    b = values.max()
    c = values.mean()
    
    dist = np.random.triangular(a,c,b,n_simulations)
    w = create_weight(name, def_team, stat_cat)
    adjusted = dist + w

    prob_sim = sum(val >= line for val in adjusted)/n_simulations
    
    return prob_sim
#_______________________________________________________________________________________________________________________



