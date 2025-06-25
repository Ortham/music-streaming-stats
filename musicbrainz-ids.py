#!/usr/bin/env python3
# /// script
# requires-python = ">=3"
# dependencies = ["psycopg[binary]"]
# ///

import argparse
from datetime import datetime
import multiprocessing
import os

import psycopg

from helpers import read_json, write_json

def connect_to_postgres(postgres_host, postgres_port, postgres_sslmode, postgres_db, postgres_user, postgres_password):
    return psycopg.connect(f"host={postgres_host} port={postgres_port} sslmode={postgres_sslmode} dbname={postgres_db} user={postgres_user} password={postgres_password}")

def get_musicbrainz_recording_ids_by_isrc(postgres_connection, track):
    isrc = track['external_ids']['isrc'].upper() if 'isrc' in track['external_ids'] else None

    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select gid from recording r
                        join isrc i on i.recording = r.id
                        where isrc is not null and isrc = %s
                    """, (isrc,))
        rows = cur.fetchall()

        if rows:
            return [str(row[0]) for row in rows]

    return []

def get_musicbrainz_recording_ids_by_name(postgres_connection, track):
    mbids = []
    for artist in track['artists']:
        with postgres_connection.cursor() as cur:
            cur.execute("""
                        select gid from recording r
                            join artist_credit_name acn on r.artist_credit = acn.artist_credit
                            where lower(r.name) = lower(%s) and lower(acn.name) = lower(%s)
                        """, (track['name'], artist['name']))
            rows = cur.fetchall()

            for row in rows:
                mbids.append(str(row[0]))

    return mbids

def get_musicbrainz_recording_ids(postgres_connection, track):
    mbids = get_musicbrainz_recording_ids_by_isrc(postgres_connection, track)

    mbids.extend(get_musicbrainz_recording_ids_by_name(postgres_connection, track))

    return list(set(mbids))

def map_track(track):
    artist_names = [a['name'].lower() for a in track['artists'] if a['name']]
    isrc = track['external_ids']['isrc'].upper().encode() if 'isrc' in track['external_ids'] else None

    return (track['uri'], isrc, track['name'].lower(), artist_names)

def map_recording(recording):
    isrc = recording[0].encode() if recording[0] is not None else None
    return (recording[1], isrc, recording[2].lower(), recording[3].lower())

def match_track(recording, track):
    if recording[1] and track[1] == recording[1]:
            return True

    if track[2] != recording[2]:
        return False

    for artist_name in track[3]:
        if artist_name == recording[3]:
            return True

    return False

def match_tracks(recordings, tracks):
    matches = []
    for recording in recordings:
        for track in tracks:
            if match_track(recording, track):
                matches.append((track[0], recording[0]))

    return matches

def match_tracks_with_queue(queue, recordings, tracks):
    queue.put(match_tracks(recordings, tracks))

def match_tracks_par(recordings, tracks):
    num_threads = os.process_cpu_count()

    recordings_per_thread = int(len(recordings) / num_threads) + 1

    print(f"Splitting {len(recordings)} recordings into chunks of {recordings_per_thread} over {num_threads} threads...")

    matches = []

    queue = multiprocessing.Queue()
    for i in range(0, len(recordings), recordings_per_thread):
        chunk = recordings[i:i + recordings_per_thread]
        process = multiprocessing.Process(target=match_tracks_with_queue, args=(queue, chunk, tracks))
        process.start()

    for i in range(num_threads):
        matches.extend(queue.get())

    return matches

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--spotify-tracks-metadata-path')
    parser.add_argument('--recordings-path')
    parser.add_argument('--output-path')
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='6543')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='musicbrainz_db')
    parser.add_argument('--postgresql-user', default='musicbrainz')
    parser.add_argument('--postgresql-password', default='musicbrainz')
    args = parser.parse_args()

    tracks_metadata = read_json(args.spotify_tracks_metadata_path)
    print('Tracks', len(tracks_metadata))

    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1
    print('Tracks with ISRCs', count)

    recording_ids_by_uri = {}
    recording_ids = []
    unmapped_track_uris = []

    if args.recordings_path:
        start = datetime.now()

        print('Loading recordings...')
        recordings = read_json(args.recordings_path)

        print('Loading data took', datetime.now() - start)

        start = datetime.now()

        recordings = [map_recording(r) for r in recordings]
        tracks = [map_track(t) for t in tracks_metadata if t['name']]

        print('Preparing data took', datetime.now() - start)

        start = datetime.now()

        matches = match_tracks_par(recordings, tracks)

        print('Matching took', datetime.now() - start)

        for [uri, id] in matches:
            if uri in recording_ids_by_uri:
                recording_ids_by_uri[uri].add(id)
            else:
                recording_ids_by_uri[uri] = set([id])

        for uri in recording_ids_by_uri:
            recording_ids.extend(recording_ids_by_uri[uri])
            recording_ids_by_uri[uri] = list(recording_ids_by_uri[uri])
    else:
        postgres_connection = connect_to_postgres(args.postgresql_host,
                                                    args.postgresql_port,
                                                    args.postgresql_sslmode,
                                                    args.postgresql_db,
                                                    args.postgresql_user,
                                                    args.postgresql_password)

        with postgres_connection:
            start = datetime.now()

            for track in tracks_metadata:
                uri = track['uri']
                track_recording_ids = get_musicbrainz_recording_ids(postgres_connection, track)

                if track_recording_ids:
                    recording_ids_by_uri[uri] = track_recording_ids
                    recording_ids.extend(track_recording_ids)
                else:
                    unmapped_track_uris.append(uri)

            print('Elapsed time', datetime.now() - start)

    print(f'Mapped {len(recording_ids_by_uri)} tracks to {len(recording_ids)} recordings ({len(set(recording_ids))} unique), leaving {len(unmapped_track_uris)} unmapped tracks')

    if args.output_path:
        content = {
            'mbids_by_spotify_uri': recording_ids_by_uri,
            'unmapped_track_uris': list(unmapped_track_uris)
        }

        write_json(args.output_path, content)

if __name__ == "__main__":
    main()
