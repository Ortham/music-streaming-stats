#!/usr/bin/env python3

import argparse
import json
import os

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def read_spotify_streams_json(dir_path):
    streams = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.json') and '_Audio_' in filename:
            file_path = os.path.join(dir_path, filename)
            streams.extend(read_json(file_path))

    return streams

def increment(count_time, stream):
    if count_time:
        return stream['ms_played']
    else:
        return 1

def check_streams(spotify_streams, spotify_tracks, musicbrainz, acousticbrainz, count_time):
    print('Counting streams...')

    streams_count = 0
    track_streams = 0
    streams_with_isrc_count = 0
    streams_in_musicbrainz_count = 0
    streams_with_genre_count = 0
    streams_with_acoustic_count = 0

    spotify_tracks = {track['uri']: track for track in spotify_tracks}

    for stream in spotify_streams:
        streams_count += increment(count_time, stream)

        if not stream['spotify_track_uri']:
            continue

        track_streams += increment(count_time, stream)

        track = spotify_tracks[stream['spotify_track_uri']]

        if 'isrc' not in track['external_ids']:
            continue

        isrc = track['external_ids']['isrc']

        streams_with_isrc_count += increment(count_time, stream)

        if isrc not in musicbrainz['mbids_by_isrc']:
            continue

        streams_in_musicbrainz_count += increment(count_time, stream)

        for mbid in musicbrainz['mbids_by_isrc'][isrc]:
            if mbid in musicbrainz['genres_by_mbid']:
                streams_with_genre_count += increment(count_time, stream)
                break

        for mbid in musicbrainz['mbids_by_isrc'][isrc]:
            if mbid in acousticbrainz:
                streams_with_acoustic_count += increment(count_time, stream)
                break

    print('Spotify streams:', streams_count)
    print('track_streams', track_streams)
    print('streams_with_isrc_count', streams_with_isrc_count)
    print('streams_in_musicbrainz_count', streams_in_musicbrainz_count)
    print('Tracks with genre', streams_with_genre_count)
    print('Tracks with acoustic metadata', streams_with_acoustic_count)

def check_tracks(spotify_tracks, musicbrainz, acousticbrainz):
    print('Counting tracks...')
    print('Spotify tracks:', len(spotify_tracks))

    track_with_isrc_count = 0
    track_in_musicbrainz_count = 0
    track_with_genre_count = 0
    track_with_acoustic_count = 0
    for track in spotify_tracks:
        if 'isrc' not in track['external_ids']:
            continue

        isrc = track['external_ids']['isrc']

        track_with_isrc_count += 1

        if isrc not in musicbrainz['mbids_by_isrc']:
            continue

        track_in_musicbrainz_count += 1

        for mbid in musicbrainz['mbids_by_isrc'][isrc]:
            if mbid in musicbrainz['genres_by_mbid']:
                track_with_genre_count += 1
                break

        for mbid in musicbrainz['mbids_by_isrc'][isrc]:
            if mbid in acousticbrainz:
                track_with_acoustic_count += 1
                break

    print('track_with_isrc_count', track_with_isrc_count)
    print('track_in_musicbrainz_count', track_in_musicbrainz_count)
    print('Tracks with genre', track_with_genre_count)
    print('Tracks with acoustic metadata', track_with_acoustic_count)

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--spotify-streams-path')
    parser.add_argument('--spotify-path')
    parser.add_argument('--musicbrainz-path')
    parser.add_argument('--acousticbrainz-path')
    args = parser.parse_args()

    spotify_streams = read_spotify_streams_json(args.spotify_streams_path)
    spotify_tracks = read_json(args.spotify_path)
    musicbrainz = read_json(args.musicbrainz_path)
    acousticbrainz = read_json(args.acousticbrainz_path)

    check_streams(spotify_streams, spotify_tracks, musicbrainz, acousticbrainz, True)
    check_streams(spotify_streams, spotify_tracks, musicbrainz, acousticbrainz, False)
    check_tracks(spotify_tracks, musicbrainz, acousticbrainz)

if __name__ == "__main__":
    main()
