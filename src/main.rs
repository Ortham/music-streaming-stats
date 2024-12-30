use std::{
    collections::{HashMap, HashSet},
    fmt::Display,
    fs::File,
    io::BufReader,
    path::PathBuf,
    time::SystemTime,
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

#[derive(Deserialize, Clone)]
struct RecordingIsrcArtist {
    isrc: Option<Isrc>,
    mbid: Mbid,
    track_name: String,
    artist_name: String,
}

#[derive(Serialize)]
struct Results<'a, 'b> {
    mbids_by_spotify_uri: HashMap<&'a str, Vec<&'b Mbid>>,
    unmapped_track_uris: Vec<&'a str>,
}

fn normalise_recording(recording: &RecordingIsrcArtist) -> RecordingIsrcArtist {
    let track_name = recording.track_name.to_lowercase();
    let artist_name = recording.artist_name.to_lowercase();

    RecordingIsrcArtist {
        mbid: recording.mbid,
        track_name,
        isrc: recording.isrc,
        artist_name,
    }
}

fn normalise_recordings(recordings: &[RecordingIsrcArtist]) -> Vec<RecordingIsrcArtist> {
    recordings.iter().map(normalise_recording).collect()
}

fn normalise_recordings_par(recordings: &[RecordingIsrcArtist]) -> Vec<RecordingIsrcArtist> {
    execute_par(recordings, normalise_recordings)
}

fn normalise_tracks(tracks: &[SpotifyTrack]) -> Vec<SpotifyTrack> {
    tracks
        .iter()
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
            external_ids: t.external_ids.clone(),
        })
        .collect()
}

fn match_track(recording: &RecordingIsrcArtist, track: &SpotifyTrack) -> bool {
    if recording.isrc.is_some() && track.external_ids.isrc == recording.isrc {
        return true;
    }

    // if !track.name.contains(&recording.track_name) && !recording.track_name.contains(&track.name) {
    if track.name != recording.track_name {
        return false;
    }

    for track_artist in &track.artists {
        // if track_artist.name.contains(&recording.artist_name)
        //     || recording.artist_name.contains(&track_artist.name)
        // {
        if track_artist.name == recording.artist_name {
            return true;
        }
    }

    false
}

fn find_matches<'a, 'b>(
    recordings: &'a [RecordingIsrcArtist],
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

fn execute_par<'a, T: Sync, O: Clone + Send>(
    items: &'a [T],
    function: impl Fn(&'a [T]) -> Vec<O> + Send + Copy,
) -> Vec<O> {
    let num_threads = usize::from(std::thread::available_parallelism().unwrap());

    let items_per_thread = (items.len() / num_threads) + 1;

    let mut iter = items.chunks(items_per_thread);

    // Collect into this to retain total order. It's not really necessary, but
    // helps give consistent results when testing with a sub-slice of input data.
    let mut thread_results = vec![Vec::new(); num_threads];

    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::scope(|s| {
        for i in 0..num_threads {
            if let Some(chunk) = iter.next() {
                let sender = sender.clone();

                s.spawn(move || {
                    let matches = function(chunk);

                    sender.send((i, matches)).unwrap();
                });
            }
        }

        for _ in 0..num_threads {
            let (i, results) = receiver.recv().unwrap();
            thread_results[i] = results;
        }
    });

    thread_results.into_iter().flatten().collect()
}

fn find_matches_par<'a, 'b>(
    recordings: &'a [RecordingIsrcArtist],
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
    let tracks = normalise_tracks(&tracks);
    println!("Left with {} tracks", tracks.len());

    println!(
        "Preparing data took {} ms",
        start.elapsed().unwrap().as_millis()
    );

    let start = SystemTime::now();

    let match_results = find_matches_par(&recordings, &tracks);

    println!("Matching took {} ms", start.elapsed().unwrap().as_millis());

    let results = process_results(&tracks, &match_results);

    let unique_matches_count = match_results.iter().collect::<HashSet<_>>().len();

    let unique_mbids_count = match_results
        .iter()
        .map(|(_, mbid)| mbid.0)
        .collect::<HashSet<_>>()
        .len();

    println!(
        "Mapped {} tracks to {} recordings ({} unique), leaving {} unmapped tracks",
        results.mbids_by_spotify_uri.len(),
        unique_matches_count,
        unique_mbids_count,
        results.unmapped_track_uris.len()
    );

    let json = serde_json::to_string_pretty(&results).unwrap();

    std::fs::write(args.output_path, json).unwrap();
}
