#!/usr/bin/env python3

import argparse
from hashlib import sha256

from helpers import read_json

def check_transformed_isrc_uniqueness(tracks, transformer_name, transformer):
    isrcs = set()
    countries = set()
    prefix_codes = set()
    prefix_and_years = set()
    for track in tracks:
        if 'isrc' in track['external_ids']:
            isrc = transformer(track['external_ids']['isrc'])
            isrcs.add(isrc)
            countries.add(isrc[:2])
            prefix_codes.add(isrc[:5])
            prefix_and_years.add(isrc[:7])

    print(f'Using transformer: {transformer_name}')
    print(f'  Found {len(isrcs)} unique ISRCs')
    print(f'  Found {len(countries)} unique country codes')
    print(f'  Found {len(prefix_codes)} unique prefix codes')
    print(f'  Found {len(prefix_and_years)} unique prefix codes and years')
    print()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spotify-tracks-metadata-path')
    args = parser.parse_args()

    tracks = read_json(args.spotify_tracks_metadata_path)

    check_transformed_isrc_uniqueness(tracks, 'identity', lambda i: i)
    check_transformed_isrc_uniqueness(tracks, 'reversed', lambda i: i[::-1])
    check_transformed_isrc_uniqueness(tracks, 'hashed', lambda i: sha256(i.encode('ascii')).digest()[:12])

if __name__ == "__main__":
    main()
