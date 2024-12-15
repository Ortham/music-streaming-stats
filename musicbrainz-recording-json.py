#!/usr/bin/env python3

import argparse
import json

from helpers import read_json, write_json

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--isrcs-json-path')
    parser.add_argument('--musicbrainz-recordings-path')
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

    mb_isrc_count = 0
    mb_recording_count = 0

    recordings = []
    recording_ids_by_isrc = {}
    recordings_by_id = {}
    if args.musicbrainz_recordings_path:
        with open(args.musicbrainz_recordings_path, encoding='utf-8') as f:
            for line in f:
                recording = json.loads(line)

                mb_recording_count += 1

                recordings.append(recording)

                if len(recording['isrcs']) == 0:
                    continue

                recording_id = recording['id']

                mb_isrc_count += len(recording['isrcs'])

                is_relevant = False
                for isrc in recording['isrcs']:
                    if isrc in isrcs:
                        recording_ids_by_isrc[isrc] = recording_id
                        is_relevant = True

                if is_relevant:
                    recordings_by_id[recording_id] = {
                        'id': recording_id,
                        'isrcs': recording['isrcs'],
                        'genres': recording['genres']
                    }

    print('MB recordings', mb_recording_count)
    print('MB ISRCs', mb_isrc_count)

    # Match recordings against Spotify tracks by comparing track name, album name and artist
    match_count = 0
    for track in tracks_metadata:
        spotify_track_name = track['name']
        spotify_album_name = track['album']['name']
        spotify_artist_name = track['artists'][0]['name']

        for recording in recordings:
            if spotify_track_name != recording['title']:
                continue

            artist_matched = False
            for relation in recording['relations']:
                if 'artist' in relation and spotify_artist_name == relation['artist']['name']:
                    artist_matched = True
                    break

            if not artist_matched:
                continue

            match_count += 1

    print('Match count', match_count)

    if args.output_path:
        recordings_metadata = {
            'mbids_by_isrc': recording_ids_by_isrc,
            'recordings_by_mbid': recordings_by_id
        }

        write_json(args.output_path, recordings_metadata)

if __name__ == "__main__":
    main()
