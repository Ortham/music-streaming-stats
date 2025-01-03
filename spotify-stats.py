#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from time import sleep

import requests

from helpers import read_json, write_json, connect_to_postgres, read_spotify_streaming_history

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

def write_streams_to_postgres(postgres_connection, streams):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                CREATE TABLE IF NOT EXISTS spotify_streams (
                    id serial PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    platform TEXT NOT NULL,
                    ms_played INTEGER NOT NULL,
                    conn_country TEXT NOT NULL,
                    ip_addr TEXT NOT NULL,
                    track_name TEXT,
                    artist_name TEXT,
                    album_name TEXT,
                    track_uri TEXT,
                    episode_name TEXT,
                    episode_show_name TEXT,
                    episode_uri TEXT,
                    reason_start TEXT NOT NULL,
                    reason_end TEXT NOT NULL,
                    shuffle BOOLEAN NOT NULL,
                    skipped BOOLEAN NOT NULL,
                    offline BOOLEAN NOT NULL,
                    offline_timestamp TIMESTAMP,
                    incognito_mode BOOLEAN NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_streams_track_uri_idx
                        ON spotify_streams (track_uri)
                    """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_streams_timestamp_idx
                        ON spotify_streams (timestamp)
                    """)

        cur.execute("TRUNCATE TABLE spotify_streams")

        print('Writing streams data to postgres...')
        for stream in streams:
            if stream['spotify_track_uri'] is None:
                # It's probably a podcast episode
                continue

            try:
                offline_timestamp = datetime.fromtimestamp(stream['offline_timestamp'] / 1000, timezone.utc) if stream['offline_timestamp'] else None
            except BaseException as e:
                print('Offline timestamp is', stream['offline_timestamp'])
                raise e

            cur.execute("INSERT INTO spotify_streams (timestamp, platform, ms_played, conn_country, ip_addr, track_name, artist_name, album_name, track_uri, reason_start, reason_end, shuffle, skipped, offline, offline_timestamp, incognito_mode) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (
                stream['ts'],
                stream['platform'],
                stream['ms_played'],
                stream['conn_country'],
                stream['ip_addr'],
                stream['master_metadata_track_name'],
                stream['master_metadata_album_artist_name'],
                stream['master_metadata_album_album_name'],
                stream['spotify_track_uri'],
                stream['reason_start'],
                stream['reason_end'],
                stream['shuffle'],
                stream['skipped'],
                stream['offline'],
                offline_timestamp, stream['incognito_mode']))

    postgres_connection.commit()

def write_albums_metadata_to_postgres(postgres_connection, tracks_metadata):
    albums_by_id = {}
    for metadata in tracks_metadata:
        albums_by_id[metadata['album']['id']] = metadata['album']

    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS spotify_albums (
                    id serial PRIMARY KEY,
                    spotify_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    release_date TEXT NOT NULL,
                    release_date_precision TEXT NOT NULL,
                    total_tracks INTEGER NOT NULL,
                    album_type TEXT NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_albums_spotify_id_idx
                        ON spotify_albums (spotify_id)
                    """)

        cur.execute("TRUNCATE TABLE spotify_albums")

        print('Writing albums data to postgres...')
        for album in albums_by_id.values():
            cur.execute("INSERT INTO spotify_albums (spotify_id, name, release_date, release_date_precision, total_tracks, album_type) VALUES (%s, %s, %s, %s, %s, %s)", (
                album['id'],
                album['name'],
                album['release_date'],
                album['release_date_precision'],
                album['total_tracks'],
                album['album_type']))

    postgres_connection.commit()


def write_tracks_metadata_to_postgres(postgres_connection, tracks_metadata):
    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS spotify_tracks (
                    id serial PRIMARY KEY,
                    spotify_id TEXT NOT NULL,
                    spotify_uri TEXT NOT NULL,
                    album_id TEXT NOT NULL,
                    isrc TEXT,
                    duration_ms INTEGER NOT NULL,
                    popularity INTEGER NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_tracks_album_id_idx
                        ON spotify_tracks (album_id)
                    """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_tracks_spotify_uri_idx
                        ON spotify_tracks (spotify_uri)
                    """)

        cur.execute("TRUNCATE TABLE spotify_tracks")

        print('Writing tracks data to postgres...')
        for track_metadata in tracks_metadata:
            cur.execute('INSERT INTO spotify_tracks (spotify_id, spotify_uri, album_id, isrc, duration_ms, popularity) VALUES (%s, %s, %s, %s, %s, %s)', (
                track_metadata['id'],
                track_metadata['uri'],
                track_metadata['album']['id'],
                track_metadata['isrc'] if 'isrc' in track_metadata else None,
                track_metadata['duration_ms'],
                track_metadata['popularity']))

    postgres_connection.commit()

def write_artists_metadata_to_postgres(postgres_connection, tracks_metadata):
    artists_by_id = {}
    for track in tracks_metadata:
        for artist in track['artists']:
            artists_by_id[artist['id']] = artist

    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS spotify_artists (
                    id serial PRIMARY KEY,
                    spotify_id TEXT NOT NULL,
                    name TEXT NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_artists_spotify_id_idx
                        ON spotify_artists (spotify_id)
                    """)

        cur.execute("TRUNCATE TABLE spotify_artists")

        print('Writing albums data to postgres...')
        for artist in artists_by_id.values():
            cur.execute("INSERT INTO spotify_artists (spotify_id, name) VALUES (%s, %s)", (
                artist['id'],
                artist['name']))

    postgres_connection.commit()

def write_track_artists_metadata_to_postgres(postgres_connection, tracks_metadata):
    artists_by_id = {}
    for track in tracks_metadata:
        for artist in track['artists']:
            artists_by_id[artist['id']] = artist

    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS spotify_track_artists (
                    id serial PRIMARY KEY,
                    track_id TEXT NOT NULL,
                    artist_id TEXT NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_track_artists_track_id_idx
                        ON spotify_track_artists (track_id)
                    """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS spotify_track_artists_artist_id_idx
                        ON spotify_track_artists (artist_id)
                    """)

        cur.execute("TRUNCATE TABLE spotify_track_artists")

        print('Writing albums data to postgres...')
        for track in tracks_metadata:
            for artist in track['artists']:
                cur.execute("INSERT INTO spotify_track_artists (track_id, artist_id) VALUES (%s, %s)", (
                    track['id'],
                    artist['id']))

    postgres_connection.commit()

def write_musicbrainz_ids_to_postgres(postgres_connection, mb_metadata):
    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS musicbrainz_recordings (
                    id serial PRIMARY KEY,
                    spotify_uri TEXT NOT NULL,
                    musicbrainz_id UUID NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS musicbrainz_recordings_spotify_uri_idx
                        ON musicbrainz_recordings (spotify_uri)
                    """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS musicbrainz_recordings_musicbrainz_id_idx
                        ON musicbrainz_recordings (musicbrainz_id)
                    """)

        cur.execute("TRUNCATE TABLE musicbrainz_recordings")

        print('Writing MusicBrainz ID data to postgres...')
        for uri in mb_metadata['mbids_by_spotify_uri']:
            for mbid in mb_metadata['mbids_by_spotify_uri'][uri]:
                cur.execute('INSERT INTO musicbrainz_recordings (spotify_uri, musicbrainz_id) VALUES (%s, %s)', (uri, mbid))

    postgres_connection.commit()


def write_musicbrainz_tags_to_postgres(postgres_connection, tags_by_recording_id):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                CREATE TABLE IF NOT EXISTS musicbrainz_recording_tags (
                    id serial PRIMARY KEY,
                    recording_id UUID NOT NULL,
                    name TEXT NOT NULL,
                    count INTEGER,
                    musicbrainz_genre_id UUID)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS musicbrainz_recording_tags_recording_id_idx
                        ON musicbrainz_recording_tags (recording_id)
                    """)

        cur.execute("TRUNCATE TABLE musicbrainz_recording_tags")

        print('Writing MusicBrainz tag data to postgres...')
        for mbid in tags_by_recording_id:
            for tag in tags_by_recording_id[mbid]:
                cur.execute('INSERT INTO musicbrainz_recording_tags (recording_id, name, count, musicbrainz_genre_id) VALUES (%s, %s, %s, %s)', (mbid, tag['name'], tag['tag_count'], tag['genre_id']))

    postgres_connection.commit()


def write_acousticbrainz_metadata_to_postgres(postgres_connection, metadata_by_mbid):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                CREATE TABLE IF NOT EXISTS acousticbrainz (
                    id serial PRIMARY KEY,
                    recording_id UUID NOT NULL,
                    is_danceable BOOLEAN,
                    gender TEXT,
                    is_acoustic BOOLEAN,
                    is_aggressive BOOLEAN,
                    is_electronic BOOLEAN,
                    is_happy BOOLEAN,
                    is_party BOOLEAN,
                    is_relaxed BOOLEAN,
                    is_sad BOOLEAN,
                    timbre TEXT,
                    is_tonal BOOLEAN,
                    is_instrumental BOOLEAN,
                    bpm SMALLINT NOT NULL,
                    chords_key TEXT NOT NULL,
                    chords_scale TEXT NOT NULL,
                    key_key TEXT,
                    key_scale TEXT)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS acousticbrainz_recording_id_idx
                        ON acousticbrainz (recording_id)
                    """)

        cur.execute("TRUNCATE TABLE acousticbrainz")

        print('Writing AcousticBrainz data to postgres...')
        for mbid in metadata_by_mbid:
            high_level = metadata_by_mbid[mbid]['high_level'] if 'high_level' in metadata_by_mbid[mbid] else {
                'is_danceable': None,
                'gender': None,
                'is_acoustic': None,
                'is_aggressive': None,
                'is_electronic': None,
                'is_happy': None,
                'is_party': None,
                'is_relaxed': None,
                'is_sad': None,
                'timbre': None,
                'is_tonal': None,
                'is_instrumental': None,
            }
            bpm = metadata_by_mbid[mbid]['low_level']['rhythm']['bpm']
            tonal = metadata_by_mbid[mbid]['low_level']['tonal']

            cur.execute('INSERT INTO acousticbrainz (recording_id, is_danceable, gender, is_acoustic, is_aggressive, is_electronic, is_happy, is_party, is_relaxed, is_sad, timbre, is_tonal, is_instrumental, bpm, chords_key, chords_scale, key_key, key_scale) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (
                mbid,
                high_level['is_danceable'],
                high_level['gender'],
                high_level['is_acoustic'],
                high_level['is_aggressive'],
                high_level['is_electronic'],
                high_level['is_happy'],
                high_level['is_party'],
                high_level['is_relaxed'],
                high_level['is_sad'],
                high_level['timbre'],
                high_level['is_tonal'],
                high_level['is_instrumental'],
                bpm,
                tonal['chords_key'],
                tonal['chords_scale'],
                tonal['key_key'],
                tonal['key_scale']
            ))

    postgres_connection.commit()

def write_owned_tracks_to_postgres(postgres_connection, acoustid_matches):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                CREATE TABLE IF NOT EXISTS owned_recordings (
                    id serial PRIMARY KEY,
                    recording_id UUID NOT NULL,
                    score DOUBLE PRECISION NOT NULL)
                """)

        cur.execute("""
                    CREATE INDEX IF NOT EXISTS owned_recordings_recording_id_idx
                        ON owned_recordings (recording_id)
                    """)

        cur.execute("TRUNCATE TABLE owned_recordings")

        print('Writing AcoustID data to postgres...')
        for match in acoustid_matches:
            cur.execute('INSERT INTO owned_recordings (recording_id, score) VALUES (%s, %s)', (match['recording_id'], match['score']))

    postgres_connection.commit()

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of JSON files containing your Spotify extended streaming history.')
    parser.add_argument('--output-path')
    parser.add_argument('--postgresql', action='store_const', const=True)
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='5432')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='postgres')
    parser.add_argument('--postgresql-user', default='postgres')
    parser.add_argument('--postgresql-password', default='password')
    parser.add_argument('--spotify-client-id')
    parser.add_argument('--spotify-client-secret')
    parser.add_argument('--spotify-tracks-metadata-path')
    parser.add_argument('--spotify-streaming-history-path')
    parser.add_argument('--acousticbrainz-metadata-path')
    parser.add_argument('--musicbrainz-ids-path')
    parser.add_argument('--musicbrainz-tags-path')
    parser.add_argument('--acoustid-matches-path')
    args = parser.parse_args()

    if args.spotify_streaming_history_path:
        streams = read_spotify_streaming_history(args.spotify_streaming_history_path)

    tracks_metadata = None
    if streams and args.spotify_client_id and args.spotify_client_secret:
        access_token = get_spotify_access_token(args.spotify_client_id, args.spotify_client_secret)
        tracks_metadata = get_all_tracks_metadata(streams, access_token, args.spotify_tracks_metadata_path)
    elif args.spotify_tracks_metadata_path:
        tracks_metadata = read_json(args.spotify_tracks_metadata_path)

    if args.postgresql:
        postgres_connection = connect_to_postgres(args.postgresql_host,
                                                  args.postgresql_port,
                                                  args.postgresql_sslmode,
                                                  args.postgresql_db,
                                                  args.postgresql_user,
                                                  args.postgresql_password)

        with postgres_connection:
            if streams:
                write_streams_to_postgres(postgres_connection, streams)

            if tracks_metadata:
                write_albums_metadata_to_postgres(postgres_connection, tracks_metadata)
                write_tracks_metadata_to_postgres(postgres_connection, tracks_metadata)
                write_artists_metadata_to_postgres(postgres_connection, tracks_metadata)
                write_track_artists_metadata_to_postgres(postgres_connection, tracks_metadata)

            if args.musicbrainz_ids_path:
                ids = read_json(args.musicbrainz_ids_path)
                write_musicbrainz_ids_to_postgres(postgres_connection, ids)

            if args.musicbrainz_tags_path:
                tags = read_json(args.musicbrainz_tags_path)
                write_musicbrainz_tags_to_postgres(postgres_connection, tags)

            if args.acousticbrainz_metadata_path:
                ab_metadata = read_json(args.acousticbrainz_metadata_path)
                write_acousticbrainz_metadata_to_postgres(postgres_connection, ab_metadata)

            if args.acoustid_matches_path:
                content = read_json(args.acoustid_matches_path)
                write_owned_tracks_to_postgres(postgres_connection, content['matches'])


if __name__ == "__main__":
    main()
