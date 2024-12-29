use std::{
    collections::HashMap, fmt::Display, fs::File, io::BufReader, path::PathBuf, time::SystemTime,
};

use clap::{arg, Parser};
use serde::{Deserialize, Deserializer, Serialize};

#[derive(Parser, Debug)]
struct Args {
    #[arg(long)]
    recordings_path: PathBuf,

    #[arg(long)]
    spotify_tracks_metadata_path: PathBuf,

    #[arg(long)]
    output_path: PathBuf,
}

#[derive(PartialEq, Clone, Copy)]
struct Isrc([u8; 12]);

impl<'de> serde::Deserialize<'de> for Isrc {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        String::deserialize(deserializer)
            .map(|s| Isrc(*s.to_uppercase().as_bytes().first_chunk::<12>().unwrap()))
    }
}

#[derive(Eq, Hash, PartialEq, Copy, Clone, Debug)]
struct Mbid(u128);

impl serde::Serialize for Mbid {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        String::serialize(&self.to_string(), serializer)
    }
}

impl<'de> serde::Deserialize<'de> for Mbid {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        String::deserialize(deserializer)
            .map(|s| Mbid(u128::from_str_radix(&s.replace("-", ""), 16).unwrap()))
    }
}

impl Display for Mbid {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let hex = format!("{:032x}", self.0);
        let with_separators = format!(
            "{}-{}-{}-{}-{}",
            &hex[..8],
            &hex[8..12],
            &hex[12..16],
            &hex[16..20],
            &hex[20..]
        );

        write!(f, "{}", with_separators)
    }
}

#[derive(Deserialize, Clone)]
struct SpotifyExternalIds {
    isrc: Option<Isrc>,
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
struct RecordingIsrcArtist {
    isrc: Option<Isrc>,
    mbid: Mbid,
    track_name: String,
    artist_name: String,
}

struct Recording {
    mbid: Mbid,
    track_name: String,
    isrcs: Vec<Isrc>,
    artist_names: Vec<String>,
}

#[derive(Serialize)]
struct Results<'a, 'b> {
    mbids_by_spotify_uri: HashMap<&'a str, Vec<&'b Mbid>>,
    unmapped_track_uris: Vec<&'a str>,
}

fn normalise_recordings(recordings: &[RecordingIsrcArtist]) -> Vec<Recording> {
    let mut recordings_by_mbid: HashMap<Mbid, Recording> = HashMap::new();
    for recording in recordings {
        let track_name = recording.track_name.to_lowercase();
        let artist_name = recording.artist_name.to_lowercase();

        recordings_by_mbid
            .entry(recording.mbid)
            .and_modify(|r| {
                if r.track_name != track_name {
                    panic!(
                        "Expected track name {}, got {} for recording {}",
                        r.track_name, track_name, r.mbid
                    );
                }

                if let Some(isrc) = recording.isrc {
                    r.isrcs.push(isrc);
                }

                r.artist_names.push(artist_name.clone());
            })
            .or_insert(Recording {
                mbid: recording.mbid,
                track_name,
                isrcs: recording.isrc.into_iter().collect(),
                artist_names: vec![artist_name.clone()],
            });
    }

    recordings_by_mbid.into_values().collect()
}

fn normalise_recordings_par(recordings: &[RecordingIsrcArtist]) -> Vec<Recording> {
    execute_par(recordings, normalise_recordings)
}

fn normalise_tracks(tracks: &[SpotifyTrack]) -> Vec<SpotifyTrack> {
    tracks
        .into_iter()
        .filter(|t| !t.name.is_empty())
        .map(|t| SpotifyTrack {
            name: t.name.to_lowercase(),
            artists: t
                .artists
                .iter()
                .filter(|a| !a.name.is_empty())
                .map(|a| SpotifyArtist {
                    name: a.name.to_lowercase(),
                })
                .collect(),
            uri: t.uri.clone(),
            external_ids: t.external_ids.clone()
        })
        .collect()
}

fn normalise_tracks_par(tracks: &[SpotifyTrack]) -> Vec<SpotifyTrack> {
    execute_par(tracks, normalise_tracks)
}

fn match_track(recording: &Recording, track: &SpotifyTrack) -> bool {
    if !recording.isrcs.is_empty() {
        if let Some(isrc) = track.external_ids.isrc {
            if recording.isrcs.contains(&isrc) {
                return true;
            }
        }
    }

    // if !track.name.contains(&recording.track_name) && !recording.track_name.contains(&track.name) {
        if track.name != recording.track_name {
        return false;
    }

    for track_artist in &track.artists {
        for recording_artist_name in &recording.artist_names {
            // if track_artist.name.contains(recording_artist_name)
                // || recording_artist_name.contains(&track_artist.name)
            // {
                if track_artist.name == *recording_artist_name {
                return true;
            }
        }
    }

    false
}

fn find_matches<'a, 'b>(
    recordings: &'a [Recording],
    tracks: &'b [SpotifyTrack],
) -> Vec<(&'b str, &'a Mbid)> {
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

fn execute_par<'a, T: Sync, O: Send>(
    items: &'a [T],
    function: impl Fn(&'a [T]) -> Vec<O> + Send + Copy
) -> Vec<O> {
    let num_threads = usize::from(std::thread::available_parallelism().unwrap());

    let items_per_thread = (items.len() / num_threads) + 1;

    let mut iter = items.chunks(items_per_thread);
    let mut matches = vec![];

    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::scope(|s| {
        for _ in 0..num_threads {
            if let Some(chunk) = iter.next() {
                let sender = sender.clone();

                s.spawn(move || {
                    let matches = function(chunk);

                    sender.send(matches).unwrap();
                });
            }
        }

        for _ in 0..num_threads {
            matches.append(&mut receiver.recv().unwrap());
        }
    });

    matches
}

fn find_matches_par<'a, 'b>(
    recordings: &'a [Recording],
    tracks: &'b [SpotifyTrack],
) -> Vec<(&'b str, &'a Mbid)> {
    execute_par(recordings, |r| find_matches(r, tracks))
}

fn process_results<'a, 'b>(
    tracks: &'a [SpotifyTrack],
    matched: &[(&'a str, &'b Mbid)],
) -> Results<'a, 'b> {
    let mut mbids_by_spotify_uri: HashMap<_, Vec<_>> = HashMap::new();

    for (key, value) in matched {
        mbids_by_spotify_uri
            .entry(*key)
            .and_modify(|v| v.push(*value))
            .or_insert(vec![value]);
    }

    let unmapped_track_uris: Vec<_> = tracks
        .iter()
        .map(|t| t.uri.as_str())
        .filter(|uri| !mbids_by_spotify_uri.contains_key(uri))
        .collect();

    Results {
        mbids_by_spotify_uri,
        unmapped_track_uris,
    }
}

fn main() {
    let args = Args::parse();

    println!("Reading Spotify tracks metadata...");
    let f = File::open(args.spotify_tracks_metadata_path).unwrap();
    let reader = BufReader::new(f);
    let tracks: Vec<SpotifyTrack> = serde_json::from_reader(reader).unwrap();
    println!("Loaded {} Spotify tracks", tracks.len());

    let start = SystemTime::now();

    println!("Reading recordings...");
    let f = File::open(args.recordings_path).unwrap();
    let reader = BufReader::new(f);
    let recordings: Vec<RecordingIsrcArtist> = serde_json::from_reader(reader).unwrap();
    println!("Loaded {} recordings", recordings.len());

    println!(
        "Loading recordings took {} ms",
        start.elapsed().unwrap().as_millis()
    );

    let start = SystemTime::now();

    println!("Normalising recordings...");
    let recordings = normalise_recordings_par(&recordings);

    println!("Normalising tracks...");
    let tracks = normalise_tracks_par(&tracks);
    println!("Left with {} tracks", tracks.len());

    println!(
        "Preparing data took {} ms",
        start.elapsed().unwrap().as_millis()
    );

    let start = SystemTime::now();

    let matched = find_matches_par(&recordings, &tracks);

    println!("Found: {} matches", matched.len());
    println!("Took {} ms", start.elapsed().unwrap().as_millis());

    let results = process_results(&tracks, &matched);

    println!(
        "Mapped {} tracks, {} tracks unmapped",
        results.mbids_by_spotify_uri.len(),
        results.unmapped_track_uris.len()
    );

    let json = serde_json::to_string_pretty(&results).unwrap();

    std::fs::write(args.output_path, json).unwrap();
}
