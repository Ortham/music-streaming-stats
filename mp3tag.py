#!/usr/bin/env python3

import argparse
import csv

from helpers import read_json, write_json

def parse_input_csv(file_path):
    tracks = []
    with open(file_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            tracks.append(row)

    return tracks

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--mp3tag-export-path')
    parser.add_argument('--spotify-tracks-metadata-path')
    parser.add_argument('--musicbrainz-ids-path')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    tracks_metadata = read_json(args.spotify_tracks_metadata_path)

    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1

    print('Tracks', len(tracks_metadata))
    print('Tracks with ISRCs', count)

    mp3tag_mbids_by_isrc = {}
    mp3tag_mbids = set()

    if args.mp3tag_export_path:
        mp3tag_files_count = 0
        mp3tag_isrc_count = 0
        mp3tag_mbid_count = 0

        rows = parse_input_csv(args.mp3tag_export_path)

        for row in rows:
            isrc = row['ISRC']
            mbid = row['MBID']

            if row['Path']:
                mp3tag_files_count += 1

            if isrc:
                mp3tag_mbids_by_isrc[isrc.upper()] = mbid
                mp3tag_isrc_count += 1

            if mbid:
                mp3tag_mbids.add(mbid)
                mp3tag_mbid_count += 1

        print('Audio files', mp3tag_files_count)
        print('Audio files with ISRCs', mp3tag_isrc_count)
        print('Audio files with MBIDs', mp3tag_mbid_count)

    mbids_by_spotify_uri = {}
    if args.musicbrainz_ids_path:
        musicbrainz = read_json(args.musicbrainz_ids_path)
        mbids_by_spotify_uri = musicbrainz['mbids_by_spotify_uri']

    existing_uris_by_mbid = {}
    for uri in mbids_by_spotify_uri:
        for mbid in mbids_by_spotify_uri[uri]:
            if mbid in existing_uris_by_mbid:
                existing_uris_by_mbid[mbid].append(uri)
            else:
                existing_uris_by_mbid[mbid] = [uri]


    owned_spotify_track_uris_matched_by_isrc = set()
    owned_spotify_track_uris_matched_by_mbid = set()
    mp3tag_mbids_by_spotify_uri = {}

    for track in tracks_metadata:
        uri = track['uri']

        if 'isrc' in track['external_ids']:
            isrc = track['external_ids']['isrc'].upper()
            if isrc in mp3tag_mbids_by_isrc:
                owned_spotify_track_uris_matched_by_isrc.add(uri)

                mbid = mp3tag_mbids_by_isrc[isrc]
                # Is this MBID already matched?
                if mbid not in existing_uris_by_mbid:
                    mp3tag_mbids_by_spotify_uri[uri] = [mbid]

        if uri in mbids_by_spotify_uri:
            for mbid in mbids_by_spotify_uri[uri]:
                if mbid in mp3tag_mbids:
                    owned_spotify_track_uris_matched_by_mbid.add(uri)

    print(f'Matched {len(owned_spotify_track_uris_matched_by_isrc)} Spotify tracks with owned tracks using ISRCs')
    print(f'Matched {len(owned_spotify_track_uris_matched_by_mbid)} Spotify tracks with owned tracks using MBIDs')
    print(f'Matched {len(owned_spotify_track_uris_matched_by_isrc | owned_spotify_track_uris_matched_by_mbid)} unique Spotify tracks with owned tracks in total')
    print(f'Found {len(mp3tag_mbids_by_spotify_uri)} track to MBID mappings (via ISRCs) that were not already known')

    output = list(owned_spotify_track_uris_matched_by_isrc | owned_spotify_track_uris_matched_by_mbid)

    write_json(args.output_path, output)


if __name__ == "__main__":
    main()
