#!/usr/bin/env python3

import argparse
from enum import Enum
import os

from helpers import read_json, read_spotify_streaming_history

def increment(target, stream):
    if target == Target.TIME:
        return stream['ms_played']
    else:
        return 1

class Target(Enum):
    STREAMS = 1
    TRACKS = 2
    TIME = 3

def check_streams(spotify_streams, spotify_tracks, musicbrainz_ids, musicbrainz_genres, acousticbrainz, acoustid_match_mbids, target):
    if target == Target.TIME:
        print('Counting time streamed...')
    elif target == Target.TRACKS:
        print('Counting tracks...')
    else:
        print('Counting streams...')

    streams_count = 0
    track_streams = 0
    streams_with_isrc_count = 0
    streams_in_musicbrainz_count = 0
    streams_with_genre_count = 0
    streams_with_acoustic_count = 0
    with_owned_count = 0

    spotify_tracks = {track['uri']: track for track in spotify_tracks}

    track_uris = set()

    for stream in spotify_streams:
        streams_count += increment(target, stream)

        uri = stream['spotify_track_uri']

        if not uri:
            continue

        if target == Target.TRACKS and uri in track_uris:
            continue

        track_uris.add(uri)

        track_streams += increment(target, stream)

        track = spotify_tracks[uri]

        if 'isrc' in track['external_ids']:
            streams_with_isrc_count += increment(target, stream)

        if uri not in musicbrainz_ids['mbids_by_spotify_uri']:
            continue

        mbids = musicbrainz_ids['mbids_by_spotify_uri'][uri]

        streams_in_musicbrainz_count += increment(target, stream)

        for mbid in mbids:
            if mbid in musicbrainz_genres:
                streams_with_genre_count += increment(target, stream)
                break

        for mbid in mbids:
            if mbid in acousticbrainz:
                streams_with_acoustic_count += increment(target, stream)
                break

        for mbid in mbids:
            if mbid in acoustid_match_mbids:
                with_owned_count += increment(target, stream)
                break

    print('total', streams_count)
    print('  of tracks', track_streams)
    print('  with ISRCs', streams_with_isrc_count)
    print('  with MBIDs', streams_in_musicbrainz_count)
    print('  with tags', streams_with_genre_count)
    print('  with acoustic metadata', streams_with_acoustic_count)
    print('  of owned tracks', with_owned_count)
    print()

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--spotify-streams-path')
    parser.add_argument('--spotify-tracks-path')
    parser.add_argument('--musicbrainz-ids-path')
    parser.add_argument('--musicbrainz-genres-path')
    parser.add_argument('--acousticbrainz-path')
    parser.add_argument('--acoustid-matches-path')
    args = parser.parse_args()

    spotify_streams = read_spotify_streaming_history(args.spotify_streams_path)
    spotify_tracks = read_json(args.spotify_tracks_path)
    musicbrainz_ids = read_json(args.musicbrainz_ids_path)
    musicbrainz_genres = read_json(args.musicbrainz_genres_path)
    acousticbrainz = read_json(args.acousticbrainz_path)
    acoustid = read_json(args.acoustid_matches_path)

    acoustid_match_mbids = set()
    for match in acoustid['matches']:
        acoustid_match_mbids.add(match['recording_id'])

    for target in Target:
        check_streams(spotify_streams, spotify_tracks, musicbrainz_ids, musicbrainz_genres, acousticbrainz, acoustid_match_mbids, target)

if __name__ == "__main__":
    main()
