#!/usr/bin/env python3

import argparse
from time import sleep

import requests

from helpers import write_json, read_spotify_streaming_history

max_tracks_per_request = 50

def get_spotify_access_token(spotify_client_id, spotify_client_secret):
    url = 'https://accounts.spotify.com/api/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': spotify_client_id,
        'client_secret': spotify_client_secret
    }
    response = requests.post(url, data)
    response.raise_for_status()

    return response.json()['access_token']

def get_track_ids(streams):
    track_ids = set()
    for stream in streams:
        track_uri = stream['spotify_track_uri']
        if track_uri:
            track_id = track_uri.split(':')[-1]
            track_ids.add(track_id)

    return list(track_ids)

def get_from_spotify(url, track_ids, spotify_access_token):
    if len(track_ids) > max_tracks_per_request:
        raise ValueError('Trying to get audio features for too many tracks at once')

    params = {'ids': ','.join(track_ids)}
    headers = {'Authorization': f'Bearer {spotify_access_token}'}

    response = requests.get(url, params=params, headers=headers)

    if response.status_code == 429 and response.headers['Retry-After']:
        retry_after_secs = response.headers['Retry-After']
        print(f'Hit Spotify API rate limit, retrying request after {retry_after_secs} seconds...')
        sleep(retry_after_secs)
        return get_from_spotify(url, track_ids, spotify_access_token)
    else:
        try:
            response.raise_for_status()
        except BaseException as e:
            print(response.json())
            raise e

    return response.json()

def get_tracks_metadata(track_ids, spotify_access_token):
    # <https://developer.spotify.com/documentation/web-api/reference/get-several-tracks>
    url = 'https://api.spotify.com/v1/tracks'

    return get_from_spotify(url, track_ids, spotify_access_token)['tracks']

def get_all_tracks_metadata(streams, spotify_access_token, output_file_path):
    track_ids = get_track_ids(streams)

    all_tracks_metadata = []
    i = 0
    while i < len(track_ids):
        print(f'Getting metadata for tracks {i} to {i + max_tracks_per_request}...')
        id_batch = track_ids[i:i + max_tracks_per_request] if i + max_tracks_per_request < len(track_ids) else track_ids[i:]
        tracks_metadata = get_tracks_metadata(id_batch, spotify_access_token)

        all_tracks_metadata.extend(tracks_metadata)
        if output_file_path:
            # Write after each request to avoid redoing requests if one fails.
            write_json(output_file_path, all_tracks_metadata)

        i += max_tracks_per_request

    return all_tracks_metadata

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of JSON files containing your Spotify extended streaming history.')
    parser.add_argument('--output-path')
    parser.add_argument('--spotify-client-id')
    parser.add_argument('--spotify-client-secret')
    parser.add_argument('--spotify-streaming-history-path')
    args = parser.parse_args()

    streams = read_spotify_streaming_history(args.spotify_streaming_history_path)

    access_token = get_spotify_access_token(args.spotify_client_id, args.spotify_client_secret)
    get_all_tracks_metadata(streams, access_token, args.output_path)

if __name__ == "__main__":
    main()
