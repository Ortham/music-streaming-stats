#!/usr/bin/env python3

import argparse
import csv

from helpers import read_json, write_json

def parse_input_csv(file_path):
    tracks = []
    with open(file_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tracks.append(row)

    return tracks

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--mbid-isrc-csv-path')
    parser.add_argument('--isrcs-json-path')
    parser.add_argument('--musicbrainz-json-path')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    tracks_metadata = read_json(args.isrcs_json_path)

    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1

    print('Tracks', len(tracks_metadata))
    print('Tracks with ISRCs', count)

    if args.mbid_isrc_csv_path:
        rows = parse_input_csv(args.mbid_isrc_csv_path)
        mbid_by_isrc = {}
        for row in rows:
            mbid_by_isrc[row['ISRC']] = row['MBID']

        print('MBIDs from CSV', len(mbid_by_isrc))

        mbid_by_spotify_uri = {}
        for track in tracks_metadata:
            if 'isrc' in track['external_ids']:
                isrc = track['external_ids']['isrc']
                if isrc in mbid_by_isrc:
                    mbid_by_spotify_uri[track['uri']] = mbid_by_isrc[isrc]

        print('Track MBIDs matched', len(mbid_by_spotify_uri))

        if args.output_path:
            write_json(args.output_path, mbid_by_spotify_uri)

    if args.musicbrainz_json_path:
        musicbrainz = read_json(args.musicbrainz_json_path)

        additional_match_count = 0
        for track in tracks_metadata:
            if 'isrc' in track['external_ids']:
                isrc = track['external_ids']['isrc']
                if isrc in mbid_by_isrc and isrc not in musicbrainz['mbids_by_isrc']:
                    additional_match_count += 1

        print('additional_match_count', additional_match_count)


if __name__ == "__main__":
    main()
