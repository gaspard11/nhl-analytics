import requests

def extract_nhl_data(**kwargs):
        # Simple endpoint: today's NHL schedule/scores
        url = "https://api-web.nhle.com/v1/score/2025-11-11"
        response = requests.get(url)
        response.raise_for_status()
        return response.json() 
def extract_game_ids(payload: dict):
        # id is a plain field on each game object, no dbt needed to get it
        return [game["id"] for game in payload.get("games", [])]


def extract_game_pbp(game_id: int):
        url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()


def extract_player_ids(payload: dict):
        scorers = [int(play['details']['scoringPlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal']
        assisters1 = [int(play['details']['assist1PlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal' and 'assist1PlayerId' in play['details']]
        assisters2 = [int(play['details']['assist2PlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal' and 'assist2PlayerId' in play['details']]

        print(list(set(scorers + assisters1+ assisters2)))
        return list(set(scorers + assisters1+ assisters2))

games_payload = extract_nhl_data()

game_ids = extract_game_ids(games_payload)
game_infos_payloads = extract_game_pbp(game_ids[0])
    

player_ids = extract_player_ids(game_infos_payloads)