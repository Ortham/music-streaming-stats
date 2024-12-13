#!/usr/bin/env python3

import argparse
import json
from time import sleep

import requests

musicbrainz_rate_limit_rps = 1

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def get_from_musicbrainz(url, params, headers):
    response = requests.get(url, params=params, headers=headers)

    if response.status_code == 404:
        return None
    if response.status_code == 503:
        retry_after_secs = 1 / musicbrainz_rate_limit_rps
        print(f'Probably hit MusicBrainz API rate limit, sleeping for {retry_after_secs} seconds...')
        sleep(retry_after_secs)
        return get_from_musicbrainz(url, params, headers)
    else:
        response.raise_for_status()

    return response.json()

def get_musicbrainz_recording_id(isrc):
    url = f'https://musicbrainz.org/ws/2/isrc/{isrc}'
    headers = {'Accept': 'application/json'}

    body = get_from_musicbrainz(url, None, headers)

    return body['recordings'][0]['id']

def get_recording_genres(musicbrainz_recording_id):
    url = f'https://musicbrainz.org/ws/2/recording/{musicbrainz_recording_id}'
    params = {'inc': 'genres'}
    headers = {'Accept': 'application/json'}

    body = get_from_musicbrainz(url, params, headers)

    return [g['name'] for g in body['genres']]

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--isrcs-json-path')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    tracks_metadata = read_json(args.isrcs_json_path)

    isrcs = set(t['external_ids']['isrc'] for t in tracks_metadata if 'isrc' in t['external_ids'])
    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1

    print('Tracks', len(tracks_metadata))
    print('Tracks with ISRCs', count)
    print('ISRCs', len(isrcs))

    isrc_recording_ids = {}
    for isrc in isrcs:
        recording_id = get_musicbrainz_recording_id(isrc.upper())

        if recording_id:
            isrc_recording_ids[isrc] = recording_id
            if args.output_path:
                write_json(args.output_path, isrc_recording_ids)

            genres = get_recording_genres(recording_id)

if __name__ == "__main__":
    main()
