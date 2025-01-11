#!/usr/bin/env python3

import argparse
from time import sleep

from helpers import read_json, write_json, read_csv

import requests

max_recordings_per_request = 25

def get_from_acousticbrainz(url, params):
    retry_after_header = 'X-RateLimit-Reset-In'

    response = requests.get(url, params=params)
    if response.status_code == 429 and response.headers[retry_after_header]:
        retry_after_secs = int(response.headers[retry_after_header])
        print(f'Hit AcousticBrainz API rate limit, retrying request after {retry_after_secs} seconds...')
        sleep(retry_after_secs)
        return get_from_acousticbrainz(url, params)
    else:
        response.raise_for_status()

    return response.json()

def get_recordings_high_level_audio_metadata(musicbrainz_recording_ids):
    url = 'https://acousticbrainz.org/api/v1/high-level'
    params = {'recording_ids': ';'.join(musicbrainz_recording_ids)}

    body = get_from_acousticbrainz(url, params)

    metadata = {}
    for key in body:
        if key == 'mbid_mapping':
            continue

        metadata[key] = body[key]['0']['highlevel']

    return metadata

def get_recordings_low_level_audio_metadata(musicbrainz_recording_ids):
    url = 'https://acousticbrainz.org/api/v1/low-level'
    params = {'recording_ids': ';'.join(musicbrainz_recording_ids)}

    body = get_from_acousticbrainz(url, params)

    metadata = {}
    for key in body:
        if key == 'mbid_mapping':
            continue

        metadata[key] = body[key]['0']

    return metadata

def get_audio_metadata(recording_ids):
    high_level = get_recordings_high_level_audio_metadata(recording_ids)
    low_level = get_recordings_low_level_audio_metadata(recording_ids)

    by_id = {}
    for id in high_level:
        by_id[id] = {
            'high_level': high_level[id]
        }

    for id in low_level:
        if id not in by_id:
            by_id[id] = {}

        by_id[id]['low_level'] = low_level[id]

    return by_id

def reduce_metadata(recording_metadata):
    if 'high_level' in recording_metadata:
        value = recording_metadata['high_level']

        recording_metadata['high_level'] = {
            'is_danceable': True if value['danceability']['value'] == 'danceable' else False,
            'gender': value['gender']['value'],
            'is_acoustic': True if value['mood_acoustic']['value'] == 'acoustic' else False,
            'is_aggressive': True if value['mood_aggressive']['value'] == 'aggressive' else False,
            'is_electronic': True if value['mood_electronic']['value'] == 'electronic' else False,
            'is_happy': True if value['mood_happy']['value'] == 'happy' else False,
            'is_party': True if value['mood_party']['value'] == 'party' else False,
            'is_relaxed': True if value['mood_relaxed']['value'] == 'relaxed' else False,
            'is_sad': True if value['mood_sad']['value'] == 'sad' else False,
            'timbre': value['timbre']['value'],
            'is_tonal': True if value['tonal_atonal']['value'] == 'tonal' else False,
            'is_instrumental': True if value['voice_instrumental']['value'] == 'instrumental' else False
        }

    if 'low_level' in recording_metadata:
        value = recording_metadata['low_level']
        recording_metadata['low_level'] = {
            'rhythm': {
                'bpm': value['rhythm']['bpm']
            },
            'tonal': {
                'chords_key': value['tonal']['chords_key'],
                'chords_scale': value['tonal']['chords_scale'],
                'key_key': value['tonal']['key_key'] if 'key_key' in value['tonal'] else None,
                'key_scale': value['tonal']['key_scale'] if 'key_scale' in value['tonal'] else None
            }
        }

def any_in(needles, haystack):
    for needle in needles:
        if needle in haystack:
            return True

    return False

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $.mbids_by_spotify_uri')
    parser.add_argument('--input-path')
    parser.add_argument('--low-level-csv-path')
    parser.add_argument('--output-path')
    parser.add_argument('--reduce-metadata', action='store_const', const=True)
    args = parser.parse_args()

    if args.reduce_metadata:
        recordings_audio_metadata = read_json(args.input_path)

        for recording_id in recordings_audio_metadata:
            reduce_metadata(recordings_audio_metadata[recording_id])

        print(f'Reduced audio metadata for {len(recordings_audio_metadata)} recordings')

        write_json(args.output_path, recordings_audio_metadata)

        exit(0)

    recordings_audio_metadata = {}
    try:
        recordings_audio_metadata = read_json(args.output_path)
        print(f'Acoustic metadata already fetched for {len(recordings_audio_metadata)} recording MBIDs')
    except Exception as e:
        print(f'Could not read file at {args.output_path}, will fetch audio metadata for all recordings.')
        pass

    input_data = read_json(args.input_path)

    low_level_mbids = set()
    if args.low_level_csv_path:
        low_level_data = read_csv(args.low_level_csv_path)
        low_level_mbids = set(r['mbid'] for r in low_level_data)
        print(f'Found low-level acoustic metadata for {len(low_level_mbids)} MBIDs')

    unique_mbids = set()
    recording_ids = set()
    for uri, mbids in input_data['mbids_by_spotify_uri'].items():
        for mbid in mbids:
            unique_mbids.add(mbid)

        for mbid in mbids:
            if mbid not in recordings_audio_metadata:
                if low_level_mbids and mbid in low_level_mbids:
                    recording_ids.add(mbid)
                    # No need to fetch for other MBIDs for this track, since we know this will have data.
                    break
                elif not low_level_mbids:
                    # We don't know if this will have data or not, so query it.
                    recording_ids.add(mbid)

                # No point querying the MBID if it's known not to have data.

        if low_level_mbids and not any_in(mbids, recording_ids):
            print(f'Could not find low-level metadata for URI {uri}')

    recording_ids = list(recording_ids)
    print(f'Fetching audio metadata for {len(recording_ids)} of {len(unique_mbids)} recordings...')

    i = 0
    while i < len(recording_ids):
        print(f'Getting metadata for recordings {i} to {i + max_recordings_per_request}...')
        id_batch = recording_ids[i:i + max_recordings_per_request] if i + max_recordings_per_request < len(recording_ids) else recording_ids[i:]
        metadata = get_audio_metadata(id_batch)

        recordings_audio_metadata |= metadata

        # Write after each request to avoid redoing requests if one fails.
        write_json(args.output_path, recordings_audio_metadata)

        i += max_recordings_per_request

    print(f'Found audio metadata for {len(recordings_audio_metadata)} recordings')

if __name__ == "__main__":
    main()
