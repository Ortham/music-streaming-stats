#!/usr/bin/env python3

import argparse

from helpers import write_json, connect_to_postgres

def get_all_musicbrainz_recordings(postgres_connection):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select isrc, gid, r.name, acn.name from recording r
                        left join isrc i on i.recording = r.id
                        join artist_credit_name acn on r.artist_credit = acn.artist_credit
                    """)
        rows = cur.fetchall()

        return [(row[0], str(row[1]), row[2], row[3]) for row in rows]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-path')
    parser.add_argument('--postgresql', action='store_const', const=True)
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='6543')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='musicbrainz_db')
    parser.add_argument('--postgresql-user', default='musicbrainz')
    parser.add_argument('--postgresql-password', default='musicbrainz')
    args = parser.parse_args()

    postgres_connection = connect_to_postgres(args.postgresql_host,
                                                args.postgresql_port,
                                                args.postgresql_sslmode,
                                                args.postgresql_db,
                                                args.postgresql_user,
                                                args.postgresql_password)

    data = get_all_musicbrainz_recordings(postgres_connection)
    write_json(args.output_path, data)


if __name__ == "__main__":
    main()
