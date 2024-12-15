#!/usr/bin/env python3

import argparse

from helpers import read_json, write_json, connect_to_postgres

def get_recording_tags(postgres_connection, musicbrainz_recording_id):
    # Not all tags are genres that are recognised by MusicBrainz, this includes
    # the genre ID if there is one.
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select tag.name, rt.count, genre.gid as genre_id
                        from recording r
                        join recording_tag rt on r.id = rt.recording
                        join tag on rt.tag = tag.id
                        left join genre on genre.name = tag.name
                        where r.gid = %s
                    """, (musicbrainz_recording_id, ))
        rows = cur.fetchall()

        return rows

def get_recording_genres(postgres_connection, musicbrainz_recording_id):
    # Not all tags are genres that are recognised by MusicBrainz, this only
    # returns tags that are genres
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select tag.name, rt.count, genre.gid as genre_id
                        from recording r
                        join recording_tag rt on r.id = rt.recording
                        join tag on rt.tag = tag.id
                        join genre on genre.name = tag.name
                        where r.gid = %s
                    """, (musicbrainz_recording_id, ))
        rows = cur.fetchall()

        return rows

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $.mbids_by_isrc')
    parser.add_argument('--input-path')
    parser.add_argument('--output-path')
    parser.add_argument('--get-all-tags', action='store_const', const=True)
    parser.add_argument('--postgresql', action='store_const', const=True)
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='6543')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='musicbrainz_db')
    parser.add_argument('--postgresql-user', default='musicbrainz')
    parser.add_argument('--postgresql-password', default='musicbrainz')
    args = parser.parse_args()

    mbids_by_spotify_uri = read_json(args.input_path)['mbids_by_spotify_uri']

    mbids = set(mbid for mbids in mbids_by_spotify_uri.values() for mbid in mbids)

    print('Tracks', len(mbids_by_spotify_uri))
    print('MBIDs', len(mbids))

    postgres_connection = connect_to_postgres(args.postgresql_host,
                                                args.postgresql_port,
                                                args.postgresql_sslmode,
                                                args.postgresql_db,
                                                args.postgresql_user,
                                                args.postgresql_password)

    recording_genres = {}
    with postgres_connection:
        for recording_id in mbids:
            if args.get_all_tags:
                genres = get_recording_genres(postgres_connection, recording_id)
            else:
                genres = get_recording_tags(postgres_connection, recording_id)
            genres = [{'name': genre[0], 'tag_count': genre[1], 'genre_id': str(genre[2])} for genre in genres]

            if genres:
                recording_genres[recording_id] = genres

    if args.output_path:
        write_json(args.output_path, recording_genres)

if __name__ == "__main__":
    main()
