#!/usr/bin/env python3

import argparse

from helpers import read_json, write_json

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing a $.unmapped_track_uris array.')
    parser.add_argument('--mapping-results-path')
    parser.add_argument('--spotify-tracks-metadata-path')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    tracks = read_json(args.spotify_tracks_metadata_path)

    tracks_by_uri = {}
    for track in tracks:
        tracks_by_uri[track['uri']] = track

    results = read_json(args.mapping_results_path)

    unmapped_tracks = []
    for uri in results['unmapped_track_uris']:
        unmapped_tracks.append(tracks_by_uri[uri])

    write_json(args.output_path, unmapped_tracks)

if __name__ == "__main__":
    main()
