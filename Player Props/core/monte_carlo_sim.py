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

DEBUG = False

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
def create_weight(name, def_team, stat_cat, k = 0.6):
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
        k = 0.2
        #zdef = float(def_index_df.loc[def_index_df['def_team'] == def_team, 'dsi'])
        player_std = find_player(name)[stat_cat].std()
        league_avg = def_league_stats(stat_cat)[0]
        league_std = def_league_stats(stat_cat)[1]
        if STAT_MAP[stat_cat][1] == 'pass':
            team_avg = pass_def(def_team)[stat_cat].mean()
        elif STAT_MAP[stat_cat][1] == 'run':
            team_avg = run_def(def_team)[stat_cat].mean()

        zdef = (team_avg - league_avg)/ league_std
    
        weight = k * player_std * (-zdef)

    else:
        if pos == 'RB':
            k = .12
        elif pos == 'WR':
            k = .23
        elif pos == 'TE':
            k = .01
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
    window = 3
    n_simulations = 10000
    df = find_player(name)
    df = df[df['week'] > df['week'].max() - window]
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


# ****** PROCESS USED TO TUNE K VALUES, WILL LATER BE DEPRECATED ONCE K IS TUNED ******
weeks = [3, 4, 5, 6, 7, 8]
import numpy as np
qbs = ['Aaron Rodgers', 'Matthew Stafford', 'Jared Goff','Dak Prescott', 'Patrick Mahomes', 'Sam Darnold', 'Josh Allen', 'Daniel Jones', 'Justin Herbert', 'Drake Maye','Jordan Love', 'Baker Mayfield', 'Caleb Williams','Bo Nix','Trevor Lawrence','Tua Tagovailoa','Jalen Hurts','Geno Smith','Cam Ward', 'Spencer Rattler']
rbs = ['Jonathan Taylor','James Cook','Bijan Robinson', 'Derrick Henry', 'Kyren Williams', 'Jahmyr Gibbs', 'Christian McCaffrey','Breece Hall', 'Travis Etienne', 'Saquon Barkley', 'Josh Jacobs','Ashton Jeanty']
wrs = ['Jaxon Smith-Njigba', 'George Pickens', 'Drake London', 'Tetairoa McMillan', 'Justin Jefferson', 'Amon-Ra St. Brown', 'Jaylen Waddle', 'Emeka Egbuka', 'Zay Flowers', 'DeVonta Smith', 'Chris Olave', 'Stefon Diggs', 'Courtland Sutton', 'Ladd McConkey', 'Khalil Shakir']
tes = ['Trey McBride', 'Travis Kelce', 'Tyler Warren', 'Dalton Schultz', 'Juwan Johnson', 'Sam LaPorta', 'Kyle Pitts', 'Hunter Henry', 'Harold Fannin Jr.', 'Dallas Goedert', 'Mark Andrews']

def get_actuals(pos, stat_cat, week,max_week_only=True):
    player_stats = load_player_data()
    player_stats = player_stats[player_stats['position'] == pos]
    if max_week_only:
        player_stats = player_stats[player_stats['week'] <= week]
    player_stats = player_stats[['player_display_name','opponent_team','week',stat_cat]]
    player_stats = player_stats[player_stats[stat_cat] != 0]
    return player_stats

def make_pred(name):
    preds = []
    actuals = []
    n_simulations = 10000
    window = 3
    for week in weeks:
        pre = get_actuals('TE','receiving_yards', week)
        pre = pre[pre['player_display_name'] == name]
        pre = pre[pre['week'] > week - window]
        values = pre['receiving_yards']
        a,b,c = values.min(),values.max(), values.mean()
        #print(week, 'Min:',a,'Max:',b,'Mean:',c)
        dist = np.random.triangular(a,c,b, n_simulations)
        pred = np.mean(dist)
        act = get_actuals('TE','receiving_yards', week+1)
        act = act[act['player_display_name'] == name]
        act = act[act['week'] == week +1]
        act = act['receiving_yards'].values
        if act.size == 0:
            continue
        else:
            preds.append(pred)
            actuals.append(act)
    if DEBUG:        
        print("DEBUG make_pred:", name, "preds:", len(preds), "acts:", len(actuals))
    return preds, actuals

'''
def weight_def(name,k):
    window = 3
    w = []
    for week in weeks:
       player = get_actuals('QB','passing_yards', week)
        player = player[player['player_display_name'] == name]
        player = player[player['week'] > week - window]
        values = player['passing_yards']
        player_std = values.std()
        
        stats = get_actuals('QB','passing_yards',week+1,max_week_only=False)
        stats = stats[stats['player_display_name'] == name]
        stats = stats[stats['week'] == week+1]
        if stats.empty:
            continue
        else:
            defense = stats['opponent_team'].values[0]
        
            team_stats = load_team_data()
            defense_stats = team_stats[team_stats['opponent_team'] == defense]
            defense_stats = defense_stats[defense_stats['week'] > week+1 -window]
            defense_values = defense_stats['passing_yards']
            defense_avg = defense_values.mean()

            league_avg, league_std = def_league_stats('passing_yards')

            zdef = (defense_avg - league_avg)/league_std

            weight = k * player_std *(-zdef)

            w.append(weight)

    return w
'''
def weight_def(name, k):
    window = 3
    w = []
    player_data = load_player_data()  # load once
    team_stats = load_team_data()     # load once

    for week in weeks:
        # Get player stats for previous `window` weeks
        player = player_data[
            (player_data['position'] == 'TE') &
            (player_data['player_display_name'] == name) &
            (player_data['week'] <= week) &
            (player_data['week'] > week - window)
        ]
        if player.empty:
            continue

        values = player['receiving_yards']
        player_std = values.std()

        # Find the opponent for NEXT week
        next_week = player_data[
            (player_data['position'] == 'TE') &
            (player_data['player_display_name'] == name) &
            (player_data['week'] == week + 1)
        ]
        if next_week.empty:
            continue

        defense = next_week['opponent_team'].iloc[0]

        # Compute defense performance over its last few games
        defense_stats = team_stats[
            (team_stats['opponent_team'] == defense) &
            (team_stats['week'] <= week) &
            (team_stats['week'] > week - window)
        ]
        if defense_stats.empty:
            continue

        defense_avg = defense_stats['receiving_yards'].mean()
        league_avg, league_std = def_league_stats('receiving_yards')
        zdef = (defense_avg - league_avg) / league_std

        weight = k * player_std * (-zdef)
        w.append(weight)

        if DEBUG:
            print(f"[DEBUG] Week {week+1}: vs {defense}, zdef={zdef:.2f}, weight={weight:.2f}")
            print("DEBUG weight_def:", name, "player_window=", player.empty, "next_week=", next_week.empty,"def_stats=", defense_stats.empty)

    return w

def tune_k_for_player(name):
    k_grid = np.linspace(0,1.2,13)

    preds, acts = make_pred(name)
    preds, acts = np.array(preds), np.array(acts)

    results = []
    for k in k_grid:
        weights = np.array(weight_def(name, k))
        adjusted = preds + weights

        mae = np.mean(np.abs(adjusted - acts))
        rmse = np.sqrt(np.mean((adjusted -acts)**2))
        results.append({'k':k, 'MAE':mae, 'RMSE':rmse})
        if DEBUG:
            print(f'[DEBUG] {name}: k={k:.2f}, MAE={mae:.2f}, RMSE={rmse:.2f}')

    res_df = pd.DataFrame(results)
    best_k = res_df.loc[res_df['RMSE'].idxmin(),'k']
    print(f'\nBest k for {name}: {best_k:.2f}')
    return res_df, best_k

best = []
for te in tes:
    print(f'\n--- {te} ---')
    res_df, best_k = tune_k_for_player(te)
    best.append(best_k)
    
best_k_te = pd.DataFrame(best)
print(best_k_te.mean())

        
        
        
        

