#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import nflreadpy as nfl
import pandas as pd
from datetime import datetime, timedelta

bettable_columns = ['passing_yards','passing_tds','completions','attempts','passing_interceptions','targets','receptions','receiving_yards','receiving_tds','carries','rushing_yards','rushing_tds']

def load_team_data(year=2025):
    return nfl.load_team_stats(year).to_pandas()

def load_player_data(year=2025):
    return nfl.load_player_stats(year).to_pandas()

def upcoming_schedule(days=7):
    schedule = nfl.load_schedules(2025).to_pandas()
    schedule['gameday'] = pd.to_datetime(schedule['gameday']).dt.date
    today = datetime.today().date()
    end_date = today + timedelta(days=7)
    upcoming = schedule[
        (schedule['gameday'] >= today) &
        (schedule['gameday'] <= end_date)
    ].sort_values("gameday")
    return upcoming

def get_pos(team,pos):
    player_stats = load_player_data()
    names = player_stats[(player_stats['team']==team.upper())&(player_stats['position']==pos.upper())]['player_display_name'].unique()
    return list(names)

def find_player(name):
    player_stats = load_player_data()
    df = player_stats[player_stats['player_display_name']==name]
    df = df.drop(columns = ['player_id','player_name','position_group','season'])
    keep_cols = ['player_display_name']+['headshot_url'] +['week']+ ['position'] + ['team'] + ['opponent_team'] + bettable_columns
    df = df[keep_cols]
    df = df.dropna(how='all',axis=1)
    df = df.loc[:,(df!=0).any(axis=0)]
    df = df.sort_values('week',ascending=True)
    return df

def pass_def(team):
    team_stats = load_team_data()
    passing_stats = ['week','team','opponent_team','completions','attempts','passing_yards','passing_tds','passing_interceptions']
    def_df = team_stats[passing_stats].copy()
    def_df['Team'] = def_df['opponent_team']
    def_df = def_df.drop(columns='opponent_team')
    def_df['Opponent'] = def_df['team']
    def_df = def_df.drop(columns='team')
    def_df['yards_per_att'] = def_df['passing_yards']/def_df['attempts']
    def_df['passing_points'] = def_df['passing_tds']*6
    def_df = def_df[def_df['Team']==team.upper()]
    return def_df

def run_def(team):
    team_stats = load_team_data()
    rushing_stats = ['week','team','opponent_team','carries','rushing_yards','rushing_tds']
    def_df = team_stats[rushing_stats].copy()
    def_df['Team'] = def_df['opponent_team']
    def_df = def_df.drop(columns='opponent_team')
    def_df['Opponent'] = def_df['team']
    def_df = def_df.drop(columns='team')
    def_df['yards_per_car'] = def_df['rushing_yards']/def_df['carries']
    def_df['rushing_points'] = def_df['rushing_tds']*6
    def_df = def_df[def_df['Team']==team.upper()]
    return def_df