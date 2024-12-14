use std::{collections::HashMap, fs::File, io::BufReader, path::PathBuf, time::SystemTime};

use clap::{arg, Parser};
use serde::{Deserialize, Deserializer, Serialize};
use uuid::Uuid;

#[derive(Parser, Debug)]
struct Args {
    #[arg(long)]
    recordings_path: PathBuf,

    #[arg(long)]
    spotify_tracks_metadata_path: PathBuf,

    #[arg(long)]
    output_path: PathBuf,
}

#[derive(Deserialize)]
struct SpotifyExternalIds {
    #[serde(default, deserialize_with = "from_str")]
    isrc: Option<[u8; 12]>,
}

#[derive(Deserialize)]
struct SpotifyTrack {
    name: String,
    artists: Vec<SpotifyArtist>,
    uri: String,
    external_ids: SpotifyExternalIds,
}

#[derive(Deserialize)]
struct SpotifyArtist {
    name: String,
}

#[derive(Deserialize)]
struct Recording {
    #[serde(deserialize_with = "from_str")]
    isrc: Option<[u8; 12]>,
    mbid: Uuid,
    track_name: String,
    artist_name: String,
}

fn from_str<'de, D>(deserializer: D) -> Result<Option<[u8; 12]>, D::Error>
where
    D: Deserializer<'de>,
{
    Option::<String>::deserialize(deserializer)
        .map(|option| option.and_then(|s| s.to_uppercase().as_bytes().first_chunk::<12>().cloned()))
}

#[derive(Serialize)]
struct Results<'a, 'b> {
    mbids_by_spotify_uri: HashMap<&'a str, Vec<&'b Uuid>>,
    unmapped_track_uris: Vec<&'a str>,
}

fn normalise_recordings(recordings: &mut [Recording]) {
    for recording in recordings {
        recording.track_name = recording.track_name.to_lowercase();
        recording.artist_name = recording.artist_name.to_lowercase();
    }
}

fn normalise_tracks(tracks: Vec<SpotifyTrack>) -> Vec<SpotifyTrack> {
    tracks
        .into_iter()
        .filter(|t| !t.name.is_empty())
        .map(|t| SpotifyTrack {
            name: t.name.to_lowercase(),
            artists: t
                .artists
                .into_iter()
                .filter(|a| !a.name.is_empty())
                .map(|a| SpotifyArtist {
                    name: a.name.to_lowercase(),
                })
                .collect(),
            uri: t.uri,
            external_ids: t.external_ids,
        })
        .collect()
}

fn match_track<'a, 'b>(
    recording: &'a Recording,
    track: &'b SpotifyTrack,
) -> bool {
    if recording.isrc.is_some() && track.external_ids.isrc == recording.isrc {
        return true
    }

    // if !track.name.contains(&recording.track_name) && !recording.track_name.contains(&track.name) {
    if track.name != recording.track_name {
        return false;
    }

    for artist in &track.artists {
        // if artist.name.contains(&recording.artist_name) || recording.artist_name.contains(&artist.name) {
        if artist.name == recording.artist_name {
            return true;
        }
    }

    false
}

fn find_matches<'a, 'b>(
    recordings: &'a [Recording],
    tracks: &'b [SpotifyTrack],
) -> Vec<(&'b str, &'a Uuid)> {
    let mut matches = Vec::new();

    for recording in recordings {
        for track in tracks {
            if match_track(recording, track) {
                matches.push((track.uri.as_str(), &recording.mbid));
            }
        }
    }

    matches
}

fn find_matches_par<'a, 'b>(
    recordings: &'a [Recording],
    tracks: &'b [SpotifyTrack],
) -> Vec<(&'b str, &'a Uuid)> {
    let num_threads = usize::from(std::thread::available_parallelism().unwrap());

    let recordings_per_thread = (recordings.len() / num_threads) + 1;

    let mut iter = recordings.chunks(recordings_per_thread);
    let mut matches = vec![];

    println!(
        "Splitting {} recordings into chunks of {} over {} threads...",
        recordings.len(),
        recordings_per_thread,
        num_threads
    );

    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::scope(|s| {
        let mut workers = vec![];

        for _ in 0..num_threads {
            if let Some(chunk) = iter.next() {
                let sender = sender.clone();

                workers.push(s.spawn(move || {
                    let matches = find_matches(chunk, tracks);

                    sender.send(matches).unwrap();
                }))
            }
        }

        for _ in 0..num_threads {
            matches.append(&mut receiver.recv().unwrap());
        }
    });

    return matches;
}

fn main() {
    let args = Args::parse();

    println!("Reading all recordings...");
    let f = File::open(args.recordings_path).unwrap();
    let reader = BufReader::new(f);
    let mut recordings: Vec<Recording> = serde_json::from_reader(reader).unwrap();
    println!("Loaded {} recordings", recordings.len());

    println!("Reading Spotify tracks metadata...");
    let f = File::open(args.spotify_tracks_metadata_path).unwrap();
    let reader = BufReader::new(f);
    let tracks: Vec<SpotifyTrack> = serde_json::from_reader(reader).unwrap();
    println!("Loaded {} Spotify tracks", tracks.len());

    println!("Normalising recordings...");
    normalise_recordings(&mut recordings);

    println!("Normalising tracks...");
    let tracks = &normalise_tracks(tracks);
    println!("Left with {} tracks", tracks.len());

    let start = SystemTime::now();

    let matched = find_matches_par(&recordings, tracks);

    println!("Found: {} matches", matched.len());
    println!("Took {} ms", start.elapsed().unwrap().as_millis());

    let mut mbids_by_spotify_uri: HashMap<&str, Vec<&Uuid>> = HashMap::new();

    for (key, value) in matched {
        mbids_by_spotify_uri
            .entry(key)
            .and_modify(|v| v.push(value))
            .or_insert(vec![value]);
    }

    let unmapped_track_uris: Vec<_> = tracks
        .iter()
        .filter(|t| !mbids_by_spotify_uri.contains_key(t.uri.as_str()))
        .map(|t| t.uri.as_str())
        .collect();

    println!(
        "Mapped {} tracks, {} tracks unmapped",
        &mbids_by_spotify_uri.len(),
        &unmapped_track_uris.len()
    );

    let results = Results {
        mbids_by_spotify_uri,
        unmapped_track_uris,
    };

    let json = serde_json::to_string_pretty(&results).unwrap();

    std::fs::write(args.output_path, json).unwrap();
}
