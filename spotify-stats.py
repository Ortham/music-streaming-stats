#!/usr/bin/env python3

import argparse
import csv
from datetime import datetime, timedelta, timezone
import os
from time import sleep

import requests

from helpers import read_json, write_json, connect_to_postgres

bucket_duration_secs = 3600
max_tracks_per_request = 50

def parse_input_json(dir_path):
    streams = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.json') and '_Audio_' in filename:
            file_path = os.path.join(dir_path, filename)
            streams.extend(read_json(file_path))

    return streams

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

def get_tracks(streams):
    tracks_by_uri = {}
    for stream in streams:
        track_uri = stream['spotify_track_uri']
        if track_uri is None:
            # It's probably a podcast episode
            continue

        if track_uri not in tracks_by_uri:
            tracks_by_uri[track_uri] = {
                'track_uri': track_uri,
                'track_name': stream['master_metadata_track_name'],
                'artist_name': stream['master_metadata_album_artist_name'],
                'album_name': stream['master_metadata_album_album_name'],
                'duration_ms': None,
                'play_time_ms': 0,
                'play_count': 0,
                'complete_play_count': 0,
            }

        tracks_by_uri[track_uri]['play_count'] += 1
        tracks_by_uri[track_uri]['play_time_ms'] += stream['ms_played']

        if stream['reason_end'] == 'trackdone':
            tracks_by_uri[track_uri]['complete_play_count'] += 1

            if 'duration_ms' not in tracks_by_uri[track_uri]:
                tracks_by_uri[track_uri]['duration_ms'] = stream['ms_played']

    tracks = list(tracks_by_uri.values())
    tracks.sort(key=lambda t: t['play_count'], reverse=True)

    return tracks_by_uri

def get_albums(tracks_by_uri):
    albums_by_name = {}
    for track in tracks_by_uri.values():
        album_name = track['album_name']
        if album_name not in albums_by_name:
            albums_by_name[album_name] = {
                'album_name': album_name,
                'artist_name': track['artist_name'],
                'tracks_play_count': 0,
                'complete_play_count': 0,
                'play_time_ms': 0,
                'track_uris': set()
            }

        albums_by_name[album_name]['tracks_play_count'] += track['complete_play_count']
        albums_by_name[album_name]['play_time_ms'] += track['play_time_ms']
        albums_by_name[album_name]['track_uris'].add(track['track_uri'])

    # The complete play count is a bit misleading, as it assumes that I've listened to all the tracks in the album at least once.
    for album in albums_by_name.values():
        track_play_counts = [tracks_by_uri[t]['complete_play_count'] for t in album['track_uris']]
        album['complete_play_count'] = min(track_play_counts)

    # This is a heuristic intended to filter out singles and EPs, and albums that haven't had a single complete play of any tracks
    albums = [album for album in albums_by_name.values() if len(album['track_uris']) > 3 and album['tracks_play_count'] > 0]

    albums.sort(key=lambda a: a['tracks_play_count'], reverse=True)

    return albums

def get_artists(tracks_by_uri):
    artists_by_name = {}
    for track in tracks_by_uri.values():
        artist_name = track['artist_name']
        if artist_name not in artists_by_name:
            artists_by_name[artist_name] = {
                'artist_name': artist_name,
                'play_count': 0,
                'complete_play_count': 0,
                'play_time_ms': 0,
                'track_uris': set()
            }

        artists_by_name[artist_name]['play_count'] += track['play_count']
        artists_by_name[artist_name]['complete_play_count'] += track['complete_play_count']
        artists_by_name[artist_name]['play_time_ms'] += track['play_time_ms']
        artists_by_name[artist_name]['track_uris'].add(track['track_uri'])

    artists = list(artists_by_name.values())
    artists.sort(key=lambda a: a['play_count'], reverse=True)

    return artists

def get_day_of_week(timestamp: datetime):
    week_days = {
        1: 'Mon',
        2: 'Tue',
        3: 'Wed',
        4: 'Thu',
        5: 'Fri',
        6: 'Sat',
        7: 'Sun'
    }
    return week_days[timestamp.isoweekday()]

def get_bucket_start_timestamp(timestamp: datetime):
    return datetime.fromtimestamp((timestamp.timestamp() // bucket_duration_secs) * bucket_duration_secs, tz=timezone.utc)

def get_hour_bucket_key(timestamp: datetime):
    return get_bucket_start_timestamp(timestamp).isoformat()

def get_hour_of_week_bucket_key(timestamp: datetime):
    day_of_week = get_day_of_week(timestamp)

    return f'{timestamp.isoweekday()} {day_of_week} {timestamp.hour:02}:00'

def get_buckets(streams, get_bucket_key):
    streams.sort(key=lambda s: s['ts'])

    buckets_by_key = {}
    for stream in streams:
        if stream['spotify_track_uri'] is None:
            # It's probably a podcast episode
            continue

        # The timestamp is when the track stopped playing, but it may have been playing across multiple buckets, and should be partially recorded against each relevant bucket to avoid over-representing playtime in any one bucket.
        end_timestamp = datetime.fromisoformat(stream['ts'])
        start_timestamp = end_timestamp - timedelta(milliseconds=stream['ms_played'])

        keys = {}
        current_ts = start_timestamp
        key = get_bucket_key(current_ts)
        end_key = get_bucket_key(end_timestamp)
        while key != end_key:
            bucket_time_remaining = timedelta(seconds=bucket_duration_secs) - (current_ts - get_bucket_start_timestamp(current_ts))

            keys[key] = bucket_time_remaining / timedelta(milliseconds=1)

            current_ts += bucket_time_remaining
            key = get_bucket_key(current_ts)

        keys[key] = (end_timestamp - current_ts) / timedelta(milliseconds=1)

        for (key, bucket_play_time_ms) in keys.items():
            if key not in buckets_by_key:
                buckets_by_key[key] = {
                    'bucket_start': key,
                    'play_time_ms': 0,
                    'streams': []
                }

            buckets_by_key[key]['play_time_ms'] += bucket_play_time_ms

            buckets_by_key[key]['streams'].append(stream)
            buckets_by_key[key]['streams'][-1]['start_ts'] = start_timestamp.isoformat()

    buckets = list(buckets_by_key.values())
    buckets.sort(key=lambda b: b['play_time_ms'], reverse=True)

    if get_bucket_key == get_hour_bucket_key:
        # Some buckets may overflow due to bad timestamps and/or playtimes. There can be many tracks with the same end timestamp (and which were played for at least one second), and even when they're not the same, the end time of one stream may be after the (end time - play duration) of the next.
        # Identical timestamps seem to often (always?) be offline = true, but the offline_timestamp field is not reliable (some streams have it set to times in 1970).
        # This block checks that all the overflowed time is accounted for by overlaps between consecutive streams.
        bucket_duration_ms = bucket_duration_secs * 1000
        for bucket in buckets:
            if bucket['play_time_ms'] <= bucket_duration_ms:
                continue

            overlap = timedelta(milliseconds=0)
            for i in reversed(range(1, len(bucket['streams']))):
                start_ts = datetime.fromisoformat(bucket['streams'][i]['start_ts'])
                previous_end_ts = datetime.fromisoformat(bucket['streams'][i - 1]['ts'])


                if previous_end_ts > start_ts:
                    overlap += previous_end_ts - start_ts

            overflow_due_to_overlap = bucket_duration_ms + (overlap / timedelta(milliseconds=1))
            unexplained_overflow = bucket['play_time_ms'] - overflow_due_to_overlap
            if unexplained_overflow > 0:
                print(f'The bucket {bucket['bucket_start']} overflows by more than the overlap between streams, leaving {unexplained_overflow} ms unexplained')

    return buckets

def increment_count(counters, key):
    if key not in counters:
        counters[key] = 0
    counters[key] += 1

def collect_stats(streams, tracks_count):
    start_reason_counts = {}
    end_reason_counts = {}
    platform_counts = {}
    country_counts = {}
    ip_addr_counts = {}
    skipped_count = 0
    complete_play_count = 0
    play_time_ms = 0

    for stream in streams:
        increment_count(start_reason_counts, stream['reason_start'])
        increment_count(end_reason_counts, stream['reason_end'])
        increment_count(platform_counts, stream['platform'])
        increment_count(country_counts, stream['conn_country'])
        increment_count(ip_addr_counts, stream['ip_addr'])

        if stream['skipped']:
            skipped_count += 1
        if stream['reason_end'] == 'trackdone':
            complete_play_count += 1

        play_time_ms += stream["ms_played"]

    return {
        'tracks_count': tracks_count,
        'plays_count': len(streams),
        'plays_time_ms': play_time_ms,
        'skipped_count': skipped_count,
        'complete_play_count': complete_play_count,
        'start_reason_counts': start_reason_counts,
        'end_reason_counts': end_reason_counts,
        'platform_counts': platform_counts,
        'country_counts': country_counts,
        'ip_addr_counts': ip_addr_counts
    }

def get_ip_addrs(stats):
    ip_addrs = [{'ip_addr': k, 'play_count': v} for (k, v) in stats['ip_addr_counts'].items()]
    ip_addrs.sort(key=lambda i: i['play_count'], reverse=True)

    return ip_addrs

def get_platforms(stats):
    platforms = [{'platform': k, 'play_count': v} for (k, v) in stats['platform_counts'].items()]
    platforms.sort(key=lambda p: p['play_count'], reverse=True)

    return platforms

def write_csv(output_path, rows):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(next(iter(rows)).keys()))

        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def write_albums_csv(output_path, albums):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['album_name','artist_name', 'tracks_play_count', 'complete_play_count', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for album in albums:
            writer.writerow(album)

def write_artists_csv(output_path, artists):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['artist_name', 'play_count', 'complete_play_count', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for artist in artists:
            writer.writerow(artist)

def write_buckets_csv(output_path, buckets):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['bucket_start', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for bucket in buckets:
            writer.writerow(bucket)

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
                    spotify_uri TEXT NOT NULL,
                    name TEXT,
                    release_date TEXT,
                    release_date_precision TEXT,
                    total_tracks INTEGER,
                    album_type TEXT)
                """)

        cur.execute("TRUNCATE TABLE spotify_albums")

        print('Writing albums data to postgres...')
        for album in albums_by_id.values():
            cur.execute("INSERT INTO spotify_albums (spotify_id, spotify_uri, name, release_date, release_date_precision, total_tracks, album_type) VALUES (%s, %s, %s, %s, %s, %s, %s)", (
                album['id'],
                album['uri'],
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
                    album_id TEXT,
                    isrc TEXT,
                    duration_ms INTEGER,
                    popularity INTEGER)
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

def write_musicbrainz_ids_to_postgres(postgres_connection, mb_metadata):
    with postgres_connection.cursor() as cur:

        cur.execute("""
                CREATE TABLE IF NOT EXISTS musicbrainz_recordings (
                    id serial PRIMARY KEY,
                    spotify_uri TEXT NOT NULL,
                    musicbrainz_id UUID NOT NULL)
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

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of JSON files containing your Spotify extended streaming history.')
    parser.add_argument('--output-path')
    parser.add_argument('-b', '--bucket-type', choices=['hour', 'hour-of-week'], default='hour')
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
    parser.add_argument('--acousticbrainz-metadata-path')
    parser.add_argument('--musicbrainz-ids-path')
    parser.add_argument('--musicbrainz-tags-path')
    parser.add_argument('input_dir_path')
    args = parser.parse_args()

    streams = parse_input_json(args.input_dir_path)

    if args.spotify_client_id and args.spotify_client_secret:
        access_token = get_spotify_access_token(args.spotify_client_id, args.spotify_client_secret)
        tracks_metadata = get_all_tracks_metadata(streams, access_token, args.spotify_tracks_metadata_path)
    elif args.spotify_tracks_metadata_path:
        tracks_metadata = read_json(args.spotify_tracks_metadata_path)

    if args.output_path:
        tracks_by_uri = get_tracks(streams)

        albums = get_albums(tracks_by_uri)
        artists = get_artists(tracks_by_uri)

        get_bucket_key = get_hour_of_week_bucket_key if args.bucket_type == 'hour-of-week' else get_hour_bucket_key
        buckets = get_buckets(streams, get_bucket_key)

        stats = collect_stats(streams, len(tracks_by_uri))
        ip_addrs = get_ip_addrs(stats)
        platforms = get_platforms(stats)

        write_json(os.path.join(args.output_path, 'spotify_streams.json'), streams)

        write_json(os.path.join(args.output_path, 'spotify_stats.json'), stats)

        write_csv(os.path.join(args.output_path, 'spotify_ip_addrs.csv'), ip_addrs)

        write_csv(os.path.join(args.output_path, 'spotify_platforms.csv'), platforms)

        write_csv(os.path.join(args.output_path, 'spotify_tracks.csv'), tracks_by_uri.values())

        write_albums_csv(os.path.join(args.output_path, 'spotify_albums.csv'), albums)

        write_artists_csv(os.path.join(args.output_path, 'spotify_artists.csv'), artists)

        write_buckets_csv(os.path.join(args.output_path, 'spotify_times.csv'), buckets)

    if args.postgresql:
        postgres_connection = connect_to_postgres(args.postgresql_host,
                                                  args.postgresql_port,
                                                  args.postgresql_sslmode,
                                                  args.postgresql_db,
                                                  args.postgresql_user,
                                                  args.postgresql_password)

        with postgres_connection:
            write_streams_to_postgres(postgres_connection, streams)

            if tracks_metadata:
                write_albums_metadata_to_postgres(postgres_connection, tracks_metadata)
                write_tracks_metadata_to_postgres(postgres_connection, tracks_metadata)

            if args.musicbrainz_ids_path:
                ids = read_json(args.musicbrainz_ids_path)
                write_musicbrainz_ids_to_postgres(postgres_connection, ids)

            if args.musicbrainz_tags_path:
                tags = read_json(args.musicbrainz_tags_path)
                write_musicbrainz_tags_to_postgres(postgres_connection, tags)

            if args.acousticbrainz_metadata_path:
                ab_metadata = read_json(args.acousticbrainz_metadata_path)
                write_acousticbrainz_metadata_to_postgres(postgres_connection, ab_metadata)


if __name__ == "__main__":
    main()
