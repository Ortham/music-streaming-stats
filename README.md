Music streaming stats
=====================

This repo contains scripts for analysing a Spotify streaming history export and visualising its stats in a Grafana dashboard, along with related scripts for matching Spotify tracks to [MusicBrainz](https://musicbrainz.org) and [AcousticBrainz](https://acousticbrainz.org/) metadata, and a few scripts related to local audio file processing.

These scripts were written as part of an exploration into my Spotify streaming history: more context can be found in a series of blog posts I wrote on the subject, starting [here](https://blog.ortham.net/posts/2024-12-21-spotify-streaming-history-part-1/).

## The scripts

Each script has its external dependencies documented as PEP 723 metadata, so they can be run simply using [uv](https://docs.astral.sh/uv/)'s `uv run`.

Alternatively, `requirements.txt` lists the same dependencies, so they can be installed in a virtualenv. For example, on Windows:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### `acousticbrainz.py`

Fetches AcousticBrainz metadata from the AcousticBrainz API given a JSON file containing a mapping of Spotify track URIs to MusicBrainz recording IDs, and writes the metadata to a JSON file. A file containing a CSV dump of the AcousticBrainz low-level feature data (can be obtained [here](https://acousticbrainz.org/download), [example](https://data.metabrainz.org/pub/musicbrainz/acousticbrainz/dumps/acousticbrainz-lowlevel-features-20220623/acousticbrainz-lowlevel-features-20220623-lowlevel.tar.zst)) can be provided to reduce the number of API requests made.

The script can also take a JSON file containing the fetched metadata and reduce it to a subset of fields that are of interest to the Grafana visualisations.

### `acoustid-fingerprint.py`

Recursively scans a given directory for audio files and calculates the [AcoustID](https://acoustid.org/) fingerprint for each found. Writes the results to a JSON file.

### `acoustid-match.py`

Given the output of `acoustid-fingerprint.py` and an [AcoustID](https://acoustid.org/) API key, attempts to match each AcoustID fingerprint to one or more MusicBrainz recordings, and writes the results to a JSON file.

### `check-mapping.py`

Given a Spotify extended streaming history (as exported from Spotify) and the outputs of `spotify-tracks.py`, `musicbrainz-ids.py` (or `spotify-tracks-to-musicbrainz-ids`), `musicbrainz-genres.py`, `acousticbrainz.py` and `acoustid-match.py`, prints how many streams, tracks and how much streaming time has been mapped from the Spotify stream history through to acoustic metadata, plus how many of those tracks have been matched with local audio files.

### `google-music-stats.py`

Reads a directory containing Google Music tracks export CSV files and combines them into a single CSV file, and prints a few stats about the tracks. Google Music exports contain much less metadata than Spotify listening history exports, so this isn't very useful.

### `isrc.py`

Given the output of `spotify-tracks.py`, checks the uniqueness of ISRCs given within that output, checking them as they are, reversed, and hashed using SHA-256.

### `merge-files.py`

Merges two input JSON files into a single output JSON file.

### `mp3tag-compare.py`

A script that can be used to compare the outputs of `acoustid-match.py` and `mp3tag.py`, and the effect that the differences have on their AcousticBrainz metadata and MusicBrainz tag metadata, using the outputs of `acousticbrainz.py` and `musicbrainz-genres.py`.

### `mp3tag.py`

Given the output of `spotify-tracks.py`, `musicbrainz-ids.py` (or `spotify-tracks-to-musicbrainz-ids`) and a CSV file containing an export of metadata from [Mp3tag](https://docs.mp3tag.de/export/), writes a JSON file containing an array of Spotify track URIs that match entries in the Mp3tag export by their ISRC or MusicBrainz recording ID.

The `mp3tag-export.mte` file provides an Mp3tag export configuration that writes the expected columns.

### `musicbrainz-api.py`

Given the output of `spotify-tracks.py`, uses the MusicBrainz API to look up the MusicBrainz recording IDs (MBIDs) that correspond to the ISRCs in that Spotify tracks metadata, and writes a JSON file containing a map of ISRCs to MBIDs.

The MusicBrainz API has a low rate limit, so for a large number of tracks it's faster to download and run a MusicBrainz database locally and query it instead, e.g. using `musicbrainz-dump-recordings.py` and `spotify-tracks-to-musicbrainz-ids`.

### `musicbrainz-dump-recordings.py`

Connects to a local MusicBrainz PostgreSQL database and dumps its recordings metadata as an array of arrays, where each inner array's elements are:

1. The ISRC string associated with the MusicBrainz recording ID, or null
2. The MusicBrainz recording ID
3. The name of the recording
4. The artist credit name associated with the recording.

A single recording can result in multiple array elements, e.g. if there are multiple artists associated with it.

You can set up a local MusicBrainz PostgreSQL database using [musicbrainz-docker](https://github.com/metabrainz/musicbrainz-docker), or [download](https://metabrainz.org/datasets/postgres-dumps#musicbrainz) a data dump and manually import the data. The script's default connection parameters assumes you're using musicbrainz-docker.

### `musicbrainz-genres.py`

Given the output of `musicbrainz-ids.py` or `spotify-tracks-to-musicbrainz-ids` and a local MusicBrainz PostgreSQL database, maps Spotify tracks to MusicBrainz tags (including genres) based on their mappings to MusicBrainz recording IDs, and writes the results to a JSON file.

### `musicbrainz-ids.py` and `spotify-tracks-to-musicbrainz-ids`

Maps Spotify tracks (using the output of `spotify-tracks.py`) to MusicBrainz recording IDs (MBIDs), and writes a JSON file containing the MBIDs by Spotify track URI, plus an array of unmapped track URIs.

MusicBrainz recordings can either be supplied as the output of `musicbrainz-dump-recordings.py`, or retrieved from a local MusicBrainz PostgreSQL database. The script's default connection parameters assumes you're using [musicbrainz-docker](https://github.com/metabrainz/musicbrainz-docker) to run the MusicBrainz database.

The Python script is very slow: a much faster alternative is the repo's `spotify-tracks-to-musicbrainz-ids` CLI utility that does the same thing, but it needs to be built from its Rust source code and only supports using the output of `musicbrainz-dump-recordings.py`, not connecting to a local MusicBrainz PostgreSQL database.

### `musicbrainz-recording-json.py`

Given the output of `spotify-tracks.py`, and a [MusicBrainz JSON data dump](https://metabrainz.org/datasets/postgres-dumps#musicbrainz), matches Spotify tracks to MusicBrainz recordings and writes the results to a JSON file.

The individual MusicBrainz JSON data dumps are incomplete, so this approach was abandoned in favour of running a local MusicBrainz DB and using `musicbrainz-dump-recordings.py`.

### `populate-db.py`

Imports data into a PostgreSQL database, creating the necessary tables and indexes. All input data sources are optional:

- your Spotify extended stream history (as exported from Spotify)
- the output of `spotify-tracks.py`
- the output of `acousticbrainz.py`
- the output of `musicbrainz-ids.py` or `spotify-tracks-to-musicbrainz-ids`
- the output of `musicbrainz-genres.py`
- the output of `acoustid-match.py`
- a CSV file with `Date` and `Cost` headings that contains a Spotify payment history.

### `spotify-csv.py`

Reads a directory of JSON files containing your Spotify extended streaming history (as exported from Spotify) and writes a set of CSV and JSON files containing various stats.

### `spotify-tracks.py`

Given Spotify API credentials and a directory of JSON files containing your Spotify extended streaming history (as exported from Spotify), retrieves track metadata for each stream and writes out a JSON file containing those tracks' metadata.

### `unmapped-spotify-tracks.py`

Given the output of `spotify-tracks.py` and `musicbrainz-ids.py` (or `spotify-tracks-to-musicbrainz-ids`), writes out a JSON file containing the metadata of tracks that were not mapped to MusicBrainz recording IDs.

## Visualising stats

It's possible to visualise the data stored in PostgreSQL using Grafana. To set that up using Podman (Docker should also work):

1. Run `podman compose up` if PostgreSQL and Grafana are not already running (or `docker compose up` if using Docker)
2. Open `http://localhost:3000/` in your web browser
3. Log in using the username `admin` and password `admin`
4. Change the admin password when prompted
5. On the getting started page, select the option to add a data source
6. Select PostgreSQL as the data source to add
7. Set the "Host URL" to `postgres:5432`, the "Database name" to `postgres`, the "Password" to `password` and "TLS/SSL Mode" to `disable`.
8. Click the "Save & test" button at the bottom of the screen - a green box should appear saying that the database connection is OK.
9. Copy the last part of the page's URL path to your clipboard (e.g. if the URL is `http://localhost:3000/connections/datasources/edit/be68m28l3yjuoa`, copy `be68m28l3yjuoa`).
10. Click the + icon in the top right corner of the screen and select the "Import dashboard" button
11. Open the `grafana-dashboard.json` file in this repository in a text editor.
12. Replace all instances of `be68m28l3yjuoa` in the file with the value that you copied.
13. Paste the JSON file content into the large text box on the "Import dashboard" page in your web browser.
14. Click the "Load" button at the bottom of the page.

**The default configuration uses hardcoded plaintext secrets and is not intended for production!**

To generate PNG images of visualisations from within Grafana, first install the image renderer plugin by running:

```
podman compose exec -it grafana grafana-cli plugins install grafana-image-renderer
```

The `queries.sql` file contains copies of the SQL queries used by the Grafana dashboard in a more readable format.
