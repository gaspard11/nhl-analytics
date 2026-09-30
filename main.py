import requests
import json
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
from pandas_gbq import to_gbq, read_gbq


credentials_json = {
  "type": "service_account",
  "project_id": "nhl-raw-data",
  "private_key_id": "a6b47a625b9ff6c79cb6e6344415b1a5f4eeacc1",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCWYvBebFoLnWaq\n6HWrVb4ULe6xU4p7lhcjizABCzsBsloIJSkzDs3rdOJGjyULJMFKUHyVFyrZzzVX\nADAKXffZtTMzv8dBnfzDsTgtJTA54F0SZir3tZuBD9FWBZ/LiQwi1tPlAKkDNRW5\nFBboDj0Kd2HeN6O68snIRQuZyTETiohhXgYVO/HVcWssnE42TTyR7M2C8//e6+Ww\nPaYuubWe3iT6yHsrH/FncGEknlrQ65p25FsXsdUyXujA6JJwqzV6+wIMW2rrZiTG\nRcyiQxGULPXJKZJ9tRbZMHpptNNfKOW1VqM6natYwx+QXYeoQvNOsktrL6aUtHGX\nQCQqQoDlAgMBAAECggEAA62p2XVnAm+4KigDcMxpGM9Czl2PvpQePsVRyETBDbqS\nDy7xggkzqjWyry0jJ9GfVLUBRxhI+QjjchxUEHzZ6h5PgU2IjydRHmxARoJpWpEN\nVbzgAi0T/6UmZqc+kFjqzhNZHXnVqHls7Zj7MnPetFnVL/1GaPU1UEu4C+vq4mJw\ndGglXiBS5g8Zm4er2o5NaoediehDW2gvCdsS/3tnPZ3XlT3iRiFo3xdghjDc5DQU\nWQWHltfyHFl6rk57M+Wie5RJIDNe5fufPoy8mD4fIsluGTlh9fCemPlAFkZ3qG3l\nNVZP/d4PnVxt0czxejXikTUnDsLPSp1wxJJxaGc/gQKBgQDPkBUrclthNgSOin3S\nCFxeJWCN0eIbaCaEQp2XC1eZ3UpzK+5X48lUj578LrSUL3AfhdoMGDNz+tEr2H+s\nNJZOHBbwzwTLChAxiz2L8uO0xLI6gRpNdgGX95H+LuUT/A3YfzT2Owmti/+y2kPH\nKPe28LngcOTByRjD+3OehkOcoQKBgQC5exwshOcb0gzvYJjqBGTQ4FNibEVGF/ty\nq2lOIY/8nINfjIB2o9sBDhOSYnKgSsUDoQzEKJxpJ6Yq0OhrNHEmaxCrwIhvbzn3\nWvmyZSg0lJ6F1kan/i+oJieoiuSE9AaCEzvQbFNlN+pc3UPeVjFmWoBwvaClAcoX\nAksCEmdZxQKBgAq/yXjgiT71jzLalT2FVVNC2Ec/8Ve+AxCiaorh+X1samigg81l\nbI3GilNBD/UEp+faBLrPngqJmL+OjL4cUxRkfAOolPT25nPKZDuVLpmz/g7tlLEi\nRV7bYWIqh46LZSQrIlEGKbAlKe7XQt9TjdCZkua+sfofMfskUI6LIYFBAoGAZH/W\nNjEU4DgiFhorALG8xoil5bBwoJgiAHHsLw90axWLAVypxp7l7V5pMGnzXfLlaR/8\nQNUYWsnG+XAUXvIdVQmyEL3Trz1/FQ3QOd8ht8vHURFXW3MY820pE+OeCoQGerhd\nMoNfdHqlnAev3GqrfaAP9AZrYrzjeTAe4FKEeVkCgYAtjQtkedJTjjuTvJz6udPZ\nrm3PJ1Rohvr8OHUcgXBWFM/upKLMx1MIb3eIscUoXHh7j8WZCSqtfFbSislr+SDU\nnCMUQLKynlUKqFr/ePlvnZylqfjf7qb/oyyXOwR5/OAZSitC1MhtFevTkvCbsDVX\nAr7R3rOkg/HRWZVGgckk+w==\n-----END PRIVATE KEY-----\n",
  "client_email": "python-bigquery@nhl-raw-data.iam.gserviceaccount.com",
  "client_id": "107395676238661265482",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/python-bigquery%40nhl-raw-data.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}




def fetch_nhl_scores():

    r = requests.get('https://api-web.nhle.com/v1/score/now')

    j = json.loads(r.text)
    games = j['games']

    df = pd.DataFrame([{
            'game_id' : g['id'],
            'game_date': g['gameDate'],
            'home_team_id': g['homeTeam']['id'],
            'away_team_id': g['awayTeam']['id'],
            'home_team_score': g['homeTeam']['score'],
            'away_team_score': g['awayTeam']['score']
        } for g in games if g['gameState'] != 'FUT'])
    print(df)
#     dataset_id = 'nhl_raw'
#     table_id = 'nhl_scores'
#     project_id = 'nhl-raw-data'
#     credentials = service_account.Credentials.from_service_account_info(credentials_json)
#     client = bigquery.Client(credentials=credentials, project=project_id)
    

#     table_ref = client.dataset(dataset_id).table(table_id)
#     table_exists = True
#     try:
#         client.get_table(table_ref)
#     except Exception:
#         table_exists = False

#     if table_exists:
#         existing_ids = read_gbq(f"SELECT game_id FROM {dataset_id}.{table_id}", project_id=project_id)
#         existing_ids_list = existing_ids['game_id'].tolist()
#         df = df[~df['game_id'].isin(existing_ids_list)]


#     to_gbq(
#             df,
#             destination_table=f"{dataset_id}.{table_id}",
#             project_id=project_id,
#             if_exists='append',
#             credentials = credentials
#         )
#     return f"{len(df)} rows written to {table_id}"
fetch_nhl_scores()