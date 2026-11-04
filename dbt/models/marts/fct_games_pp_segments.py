"""
fct_games_pp: every game cut into segments of constant strength (5v5, 5v4, 4v4, 3v3...),
one row per segment, with the official NHL power-play opportunities.

The penalty box is replayed penalty by penalty with simulate_game (this file is the reference
version: a dbt Python model can't import another file of the project).

Power plays are counted two ways:
  - POWER_PLAY_NUMBER: consecutive uneven segments with the same team on the power play
    (5v4 -> 5v3 -> 5v4 is one stretch; 5v4 -> 4v4 -> 5v4 is two)
  - PP_OPPORTUNITIES (official NHL count): each penalty served that gave the other team a man
    advantage, credited to the first power-play segment it overlaps. Coincidental and cancelled
    penalties never count. A PP goal during a major that keeps going is a new opportunity (+1).
"""


# ---------------------------------------------------------------------------------------------
# Step 1 - simulation of one game
#   input : events = goals and penalty sets in time order (see model(), step 3)
#   output: changes = strength changes [{'time_seconds', 'var_home', 'var_away'}]
#           served  = penalties served [(side, start_seconds, end_seconds)]
#           extra   = PP goals during a major that keeps going [(pp_side, time_seconds)]
# ---------------------------------------------------------------------------------------------

def simulate_game(events, game_type, game_end):
    changes = []
    served = []      # each penalty that went in the box: (side, start, end)
    extra = []       # PP goals during a major that keeps going: (pp_side, time_seconds)
    penalty_box = {'home': {'effective':[],'waiting': [], 'subbed' : []}, 'away':{'effective':[],'waiting': [], 'subbed' : []}}


    def add_penalty_to_box(penalty):
        side = penalty['side']
        if len(penalty_box[side]['effective']) < 2:
            penalty_box[side]['effective'].append(penalty)
            add_event_expiring_penalty(penalty, events[i]['time_seconds'])
        else:
            penalty_box[side]['waiting'].append(penalty)
        return

    def release_penalty(penalty):
        side = penalty['side']
        penalty_box[side]['effective'].remove(penalty)
        # expired or ended by a goal: record it (4v4 coincidental minors never create a PP)
        if not penalty.get('coincidental'):
            served.append((side, penalty['starting'], events[i]['time_seconds']))
        if penalty.get('next'):
            add_penalty_to_box(penalty['next'])
        elif penalty_box[side]['waiting']:
            nxt = min(penalty_box[side]['waiting'], key=lambda p: (p['given'], p['kind'] == 'major', p['sort_order']))
            penalty_box[side]['waiting'].remove(nxt)
            add_penalty_to_box(nxt)
        return

    def new_penalties(penalty_set, time_seconds):
        def player_key(p):
            return p['player'] if p.get('player') is not None else ('event', p['event_id'])
        minors_home = [p for p in penalty_set if p['side'] == 'home' and p['kind'] == 'minor']
        minors_away = [p for p in penalty_set if p['side'] == 'away' and p['kind'] == 'minor']
        double_minors_home = [p for p in penalty_set if p['side'] == 'home' and p['kind'] == 'double minor']
        double_minors_away = [p for p in penalty_set if p['side'] == 'away' and p['kind'] == 'double minor']
        majors_home = [p for p in penalty_set if p['side'] == 'home' and p['kind'] == 'major']
        majors_away = [p for p in penalty_set if p['side'] == 'away' and p['kind'] == 'major']

        total_minors_home = list(minors_home)
        total_minors_away = list(minors_away)

        for p in double_minors_home:
            total_minors_home.append(dict(p, kind='minor'))
            total_minors_home.append(dict(p, kind='minor'))

        for p in double_minors_away:
            total_minors_away.append(dict(p, kind='minor'))
            total_minors_away.append(dict(p, kind='minor'))
            

        resulting_penalties = []

        


        if (len(total_minors_home) == 1 and len(total_minors_away) == 1
                and len(majors_home) == len(majors_away)    # equal majors cancel each other
                and penalty_box['home']['effective'] == [] and penalty_box['away']['effective'] == []) and not any(end > time_seconds for end in penalty_box['home']['subbed']) and not any(end > time_seconds for end in penalty_box['away']['subbed']):
            resulting_penalties.append(dict(minors_home[0], coincidental=True))
            resulting_penalties.append(dict(minors_away[0], coincidental=True))
            # the cancelled majors are served with substitution but stay on the clock
            for side in ('home', 'away'):
                penalty_box[side]['subbed'] += [time_seconds + 300] * len(majors_home)
        else:
            # captain's choice: keep as many men on the ice as possible -> cancel first the
            # penalties of the players with the fewest penalties (whole players leave the box)
            count = {}
            for p in total_minors_home + total_minors_away + majors_home + majors_away:
                count[player_key(p)] = count.get(player_key(p), 0) + 1
            for penalties in (total_minors_home, total_minors_away, majors_home, majors_away):
                penalties.sort(key=lambda p: count[player_key(p)])   # stable: ties keep their order

            kept_minors = total_minors_home[len(total_minors_away):] + total_minors_away[len(total_minors_home):]
            kept_majors = majors_home[len(majors_away):] + majors_away[len(majors_home):]
            # cancelled penalties are served with substitution but stay on the clock
            cancelled_minors = min(len(total_minors_home), len(total_minors_away))
            cancelled_majors = min(len(majors_home), len(majors_away))
            for side in ('home', 'away'):
                penalty_box[side]['subbed'] += [time_seconds + 120] * cancelled_minors
                penalty_box[side]['subbed'] += [time_seconds + 300] * cancelled_majors

            by_player = {}
            for p in kept_majors:
                by_player.setdefault(player_key(p), []).append(p)
            for p in kept_minors:
                by_player.setdefault(player_key(p), []).append(p)

            for pieces in by_player.values():
                first = pieces[0]
                if len(pieces) > 1:
                    for j in range(len(pieces)-1):
                        pieces[j]['next'] = pieces[j+1]
                resulting_penalties.append(first)

        
            # last 5 min / OT: after cancelling, if what's left is one major for one team and
            # one minor or double minor (one group) for the other, only the differential is
            # served, as a major (3:00 against a minor, 1:00 against a double minor)
            if (time_seconds >= 3300 and len(kept_majors) == 1 and len(kept_minors)> 0) and len({player_key(p) for p in kept_minors}) == 1:
                major = kept_majors[0]
                group = kept_minors
                if major['side'] != group[0]['side']:
                    resulting_penalties = [dict(major, seconds=300 - 120 * len(group))]

        resulting_penalties.sort(key=lambda p: (p['kind'] == 'major', p['sort_order']))
        for p in resulting_penalties:
            add_penalty_to_box(p)

        return

    def add_event_expiring_penalty(penalty, time_seconds):
        # the penalty starts now; schedule its expiry as a new event in the events list
        durations = {'minor': 120, 'major': 300}
        penalty['starting'] = time_seconds
        expiring_event = {
            'type': 'expiring_penalty',
            'side': penalty['side'],
            'event_id': penalty['event_id'],
            'time_seconds': time_seconds + penalty.get('seconds', durations[penalty['kind']]),
        }
        # insert after the current event, after every event at the same second or earlier
        # (a goal scored the second a penalty ends is still processed before the expiry)
        pos = i + 1
        while pos < len(events) and events[pos]['time_seconds'] <= expiring_event['time_seconds']:
            pos += 1
        events.insert(pos, expiring_event)
        return

    def releasable_penalties(penalty_box, side):
        res = []
        penalties = penalty_box[side]['effective']
        for p in penalties:
            if p['kind'] == 'minor' and not p.get('coincidental'):
                res.append(p)
        return res


    def goal(event):
        release_side = 'home'
        if event['side'] == 'home':
            release_side = 'away'
        candidates = releasable_penalties(penalty_box, release_side)
        pp = len(penalty_box[release_side]['effective']) > len(penalty_box[event['side']]['effective'])
        if candidates and pp:
            released_penalty = min(candidates, key=lambda p: (p['starting'], p['sort_order']))
            penalty_expiring_event = next((e for e in events[i+1:] if e['type'] == 'expiring_penalty' and e['event_id'] == released_penalty['event_id']), None)
            if penalty_expiring_event: events.remove(penalty_expiring_event)
            release_penalty(released_penalty)

        # official stats: a PP goal during a major that keeps going is a new PP opportunity
        # (checked after the release: a minor ended by the goal doesn't count)
        still_pp = len(penalty_box[release_side]['effective']) > len(penalty_box[event['side']]['effective'])
        if still_pp and any(p['kind'] == 'major' for p in penalty_box[release_side]['effective']):
            extra.append((event['side'], event['time_seconds']))


            

    def expiring_penalty(event):
        effective = penalty_box[event['side']]['effective']
        penalty = next((p for p in effective if p['event_id'] == event['event_id']), None)
        release_penalty(penalty)
        return

    def add_change(time_seconds, var_home,var_away):
        if var_home != 0 or var_away != 0:
            changes.append({'time_seconds' : time_seconds, 'var_home' : var_home, 'var_away': var_away})
        return

    def skaters(time_seconds):
        box_home = len(penalty_box['home']['effective'])
        box_away = len(penalty_box['away']['effective'])

        if game_type == 'regular_season'and  time_seconds >= 3600:
            home_skaters  = 3 + max(0, box_away - box_home)
            away_skaters  = 3 + max(0, box_home - box_away)
        else:
            home_skaters  = 5 - box_home
            away_skaters  = 5 - box_away
            
        return (home_skaters,away_skaters)

    def step(event):
        event_type = event['type']
        if event_type == 'penalty_set':
            new_penalties(event['penalties'], event['time_seconds'])
        elif event_type == 'goal':
            goal(event)
        elif event_type == 'ot_start': pass
        else:
            expiring_penalty(event)
        return

    
    

    if game_type == 'regular_season' and game_end> 3600:
        pos = 0
        while pos < len(events) and events[pos]['time_seconds'] <= 3600 :
            pos += 1
        events.insert(pos, {'type': 'ot_start', 'time_seconds': 3600} )
    
    i=0
    prev_time = 0
    while i < len(events):
        event = events[i]
        if event['time_seconds'] >= game_end: break
        skaters_before = skaters(prev_time)
        step(event)
        skaters_after = skaters(event['time_seconds'])
        add_change(event['time_seconds'],skaters_after[0] - skaters_before[0] ,skaters_after[1] - skaters_before[1])
        i+=1
        prev_time = event['time_seconds']

    # penalties still in the box when the game ends (the waiting ones never started)
    for side in ('home', 'away'):
        for p in penalty_box[side]['effective']:
            if not p.get('coincidental'):
                served.append((side, p['starting'], game_end))

    return changes, served, extra

# ---------------------------------------------------------------------------------------------
# dbt model
# ---------------------------------------------------------------------------------------------

def model(dbt, session):
    import pandas as pd

    from snowflake.snowpark import functions as F

    # incremental: each run rebuilds only the games with newly fetched events (all their segments
    # are deleted, then inserted again). to_pandas() needs pyarrow too: without it Snowflake
    # reports "'pandas' is not installed"
    dbt.config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="game_id",
        packages=["pandas", "pyarrow"],
    )

    # ---------- Step 2 - load (runs in Snowflake), then pandas ----------
    source = dbt.ref("fct_games_events")
    selected = source.filter("event_type in ('goal', 'penalty', 'game-end') and period_descriptor <> 'SO'")

    if dbt.is_incremental:
        # games with events fetched since the last run -> replay those games entirely
        # (all their events, not only the new ones: the simulation needs the whole game)
        last_fetched = session.sql(f"select max(t.fetched_at) from {dbt.this} t").collect()[0][0]
        if last_fetched is not None:
            new_games = source.filter(F.col("fetched_at") > F.lit(last_fetched)).select("game_id").distinct()
            selected = selected.filter(F.col("game_id").isin(new_games))

    events = (
        selected
        .select_expr(
            "game_id", "event_id", "sort_order", "event_type", "team_id", "player_1_id",
            "period_number", "period_descriptor", "time_in_period",
            "details:typeCode::string as type_code",
            "details:duration::int as duration",
            "fetched_at",
        )
        .to_pandas()
    )
    games = dbt.ref("fct_games").select("game_id", "home_team_id", "away_team_id").to_pandas()

    # Snowflake returns uppercase column names
    events.columns = events.columns.str.lower()
    games.columns = games.columns.str.lower()

    # seconds since the start of the game
    mm_ss = events["time_in_period"].str.split(":", expand=True).astype(int)
    # Snowflake sends small numbers as small types (period_number arrives as int8, max 127):
    # cast to int64 before multiplying, or 1200 overflows
    events["period_number"] = events["period_number"].astype("int64")
    events["time_seconds"] = (events["period_number"] - 1) * 1200 + mm_ss[0] * 60 + mm_ss[1]

    events = events.sort_values(["game_id", "sort_order"])
    events = events.astype(object).where(events.notna(), None)   # NaN -> None
    events = events.merge(games, on="game_id", how="inner")       # adds home/away team ids

    # ---------- Step 3 - convert each game to the simulate_game input format ----------
    def penalty_kind(type_code, duration):
        """'minor', 'double minor', 'major', or None when the penalty doesn't change the manpower."""
        if type_code in ("MIN", "BEN"):
            return "double minor" if duration == 4 else "minor"
        if type_code in ("MAJ", "MAT"):
            return "major"
        return None  # MIS, GAM, PS

    def situation(home, away):
        if home > away:
            return 'PP home'
        if away > home:
            return 'PP away'
        return 'Even'
    
    rows = []                                                      # one dict per segment, all games
    for game_id, g in events.groupby("game_id", sort=False):     # 1. one game at a time
        home_id = g["home_team_id"].iloc[0]
        game_type = "regular_season" if (game_id // 10000) % 100 == 2 else "playoffs"
        game_end = int(g["time_seconds"].max())
        fetched_at = g["fetched_at"].max()                          # copied on each segment

        game_events = []
        for e in g.to_dict("records"):                              # 2. its events, in sort_order
            if e['event_type'] == 'goal':
                row = { 'type': 'goal',  'time_seconds': e['time_seconds'], 'side': 'home' if e['team_id'] == home_id else 'away'}
                game_events.append(row)
            elif e['event_type'] == 'penalty':
                kind = penalty_kind(e['type_code'], e['duration'])
                if kind is None:
                    continue
                penalty = {'side': 'home' if e['team_id'] == home_id else 'away', 
                           'kind': kind,
                           'event_id' : e['event_id'],
                           'given': e['time_seconds'],
                           'sort_order' : e['sort_order'],
                           'player' : int(e['player_1_id']) if e['player_1_id'] else None }
                # penalties called at the same second -> same penalty set
                if any(row['type'] == 'penalty_set' and row['time_seconds'] == penalty['given'] for row in game_events):
                    penalty_set = next(row for row in game_events if row['type'] == 'penalty_set' and row['time_seconds'] == penalty['given'])
                    penalty_set['penalties'].append(penalty)
                else:
                    row = {'type': 'penalty_set', 'time_seconds' : e['time_seconds'], 'penalties' : [penalty]}
                    game_events.append(row)
                
        changes, served, extra = simulate_game(game_events, game_type, game_end)

        # ---------- Step 4 - changes -> segments ----------
        # 1. combine the changes of the same second (two penalties ending together...)
        merged = {}
        for c in changes:
            h, a = merged.get(c['time_seconds'], (0, 0))
            merged[c['time_seconds']] = (h + c['var_home'], a + c['var_away'])

        # 2. close the current segment at each change, then apply it
        segment_number = 0

        def add_segment(start, end, home, away):
            nonlocal segment_number
            if end <= start:
                return                                   # no 0-second segments
            segment_number += 1
            rows.append({
                'game_id': game_id,
                'fetched_at': fetched_at,
                'segment_number': segment_number,
                'starting_time_seconds': start,
                'ending_time_seconds': end,
                'skaters_home': home,
                'skaters_away': away,
                'situation': situation(home, away),
                'pp_opportunities': 0,                   # filled in step 4.4
            })

        home, away, start = 5, 5, 0
        for t, (var_home, var_away) in sorted(merged.items()):
            if var_home == 0 and var_away == 0:
                continue                                 # changes that cancel out: same strength
            add_segment(start, t, home, away)
            home, away, start = home + var_home, away + var_away, t

        # 3. last segment, until the end of the game
        add_segment(start, game_end, home, away)

        # 4. official PP opportunities: each penalty served that gave the other team a man
        #    advantage, credited to the first power-play segment it overlaps
        game_rows = rows[-segment_number:]               # this game's segments (same dicts as rows)
        for side, piece_start, piece_end in served:
            beneficiary = 'PP away' if side == 'home' else 'PP home'
            for seg in game_rows:
                if (seg['situation'] == beneficiary
                        and seg['starting_time_seconds'] < piece_end
                        and piece_start < seg['ending_time_seconds']):
                    seg['pp_opportunities'] += 1
                    break                                # a penalty counts only once

        # PP goal during a major that keeps going: +1 to the PP segment going on after the goal
        # (start <= t: when the goal ended a minor too, that segment starts at the goal)
        for side, t in extra:
            for seg in game_rows:
                if (seg['situation'] == 'PP ' + side
                        and seg['starting_time_seconds'] <= t < seg['ending_time_seconds']):
                    seg['pp_opportunities'] += 1
                    break

    # ---------- Step 5 - output columns ----------
    if not rows:
        # incremental run with no new games: return the existing table's columns with no rows
        return session.table(str(dbt.this)).limit(0)

    segments = pd.DataFrame(rows).merge(games, on="game_id", how="left")
    segments["fetched_at"] = pd.to_datetime(segments["fetched_at"])
    start, end = segments["starting_time_seconds"], segments["ending_time_seconds"]

    def mmss(seconds):
        return (seconds // 60).astype(str).str.zfill(2) + ":" + (seconds % 60).astype(str).str.zfill(2)

    # periods are 20 min (regular-season OT is period 4, from 60:00). A segment ending exactly at
    # the end of a period shows "P1 20:00", not "P2 00:00"
    segments["start_period"] = start // 1200 + 1
    segments["start_time_in_period"] = mmss(start % 1200)
    segments["end_period"] = (end - 1) // 1200 + 1
    segments["end_time_in_period"] = mmss((end - 1) % 1200 + 1)
    segments["duration_seconds"] = end - start

    home, away = segments["skaters_home"], segments["skaters_away"]
    segments["strength"] = home.astype(str) + "v" + away.astype(str)          # from the home side
    segments["pp_team_id"] = segments["home_team_id"].where(home > away, segments["away_team_id"].where(away > home))
    segments["pk_team_id"] = segments["away_team_id"].where(home > away, segments["home_team_id"].where(away > home))

    # stretch number: consecutive uneven segments with the same team on the power play
    previous_pp_team = segments.groupby("game_id")["pp_team_id"].shift()
    new_pp = segments["pp_team_id"].notna() & (segments["pp_team_id"] != previous_pp_team)
    segments["power_play_number"] = new_pp.groupby(segments["game_id"]).cumsum().where(segments["pp_team_id"].notna())

    segments = segments[[
        "game_id", "segment_number", "power_play_number", "pp_opportunities",
        "home_team_id", "away_team_id", "pp_team_id", "pk_team_id",
        "situation", "strength", "skaters_home", "skaters_away",
        "start_period", "start_time_in_period", "end_period", "end_time_in_period",
        "starting_time_seconds", "ending_time_seconds", "duration_seconds",
        "fetched_at",
    ]]

    # nullable integers (null on even strength) instead of floats
    for col in ("power_play_number", "pp_team_id", "pk_team_id"):
        segments[col] = segments[col].astype("Int64")

    segments.columns = segments.columns.str.upper()   # lowercase names would become quoted columns
    return segments
