-- These queries use the $__timeFilter, $__timeGroup and $__timeGroupAlias Grafana macros and the $__interval Grafana variable. $__interval should be set to produce up to about 12 data points, or the graphs will be too busy to be readable.

-- Stream counts
with tracks as
  (select distinct on (ss.track_uri) ss.track_uri, owr.id
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join owned_recordings owr on owr.recording_id = mr.musicbrainz_id)
  select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Completed streams",
    count(*) filter (where tracks.id is not null) as "Owned track streams",
    count(*) filter (where tracks.id is null and reason_end = 'trackdone') as "Unowned track completed streams"
  from spotify_streams ss
  left join tracks on ss.track_uri = tracks.track_uri
  where $__timeFilter(timestamp);

-- Track, album and artist counts
select
    count(distinct ss.track_uri) "Tracks",
    count(distinct album_id) "Albums",
    count(distinct artist_id) "Artists"
  from spotify_streams ss
  join spotify_tracks st on ss.track_uri = st.spotify_uri
  join spotify_albums sa on st.album_id = sa.spotify_id
  join spotify_track_artists sta on sta.track_id = st.spotify_id
  where $__timeFilter(timestamp);

-- Total and average stream lengths
with tracks as
    (select distinct on (ss.track_uri) ss.track_uri, owr.id
      from spotify_streams ss
      join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
      join owned_recordings owr on owr.recording_id = mr.musicbrainz_id),
  complete_albums as
    (select name, album_id, album_type, total_tracks from
      (select name, album_id, album_type, total_tracks, count(*) as tracks
        from
          (select distinct on (track_uri) name, album_id, total_tracks, album_type
            from spotify_streams ss
            join spotify_tracks st on st.spotify_uri = ss.track_uri
            join spotify_albums sa on sa.spotify_id = st.album_id
            where $__timeFilter(timestamp) and reason_end = 'trackdone')
        group by album_id, name, album_type, total_tracks)
      where tracks = total_tracks
      order by total_tracks desc)
  select sum(ms_played) "Total",
      sum(ms_played) filter (where reason_end = 'trackdone') as "Completed",
      sum(ms_played) filter (where tracks.id is not null) as "Owned tracks",
      sum(ms_played) filter (where tracks.id is null and reason_end = 'trackdone') as "Unowned tracks (completed)",
      sum(ms_played) filter (where ca.album_id is not null) as "Complete albums, singles and compilations",
      avg(ms_played) as "Average stream length",
      avg(ms_played) filter (where reason_end = 'trackdone') as "Average complete stream length",
      avg(ms_played) filter (where skipped = true
        or reason_end in ('backbtn', 'unknown', 'endplay', 'fwdbtn')) as "Mean time before skip"
    from spotify_streams ss
    join spotify_tracks st on st.spotify_uri = ss.track_uri
    left join tracks on ss.track_uri = tracks.track_uri
    left join complete_albums ca on ca.album_id = st.album_id
    where $__timeFilter(timestamp);

-- Time streamed
with tracks as
  (select distinct on (ss.track_uri) ss.track_uri, owr.id
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join owned_recordings owr on owr.recording_id = mr.musicbrainz_id)
  select sum(ms_played) as "all tracks",
    sum(ms_played) filter (where tracks.id is not null) as "owned tracks",
    sum(ms_played) filter (where tracks.id is null) as "unowned tracks",
    $__timeGroupAlias(timestamp, $__interval)
  from spotify_streams ss
  left join tracks on ss.track_uri = tracks.track_uri
  where $__timeFilter(timestamp)
  group by time;

-- Time streamed per track
select sum(ms_played), track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri
  order by sum desc;

-- Time streamed per hour of the week
select sum, label
  from (select
      extract(isodow from timestamp) as day,
      extract(hour from timestamp) as hour,
      to_char(timestamp, 'Day HH24:00') as label,
      sum(ms_played) as sum
    from spotify_streams where $__timeFilter(timestamp)
    group by label, day, hour
    order by day, hour);

-- Stream end reasons
select $__timeGroupAlias(timestamp, $__interval), reason_end as metric, count(*)
  from spotify_streams where $__timeFilter(timestamp)
    and reason_end not in ('', 'appload', 'clickrow', 'playbtn', 'popup', 'uriopen', 'unknown')
  group by time, reason_end
  order by time;

-- Streams per platform
select count(*) as value, platform as metric, $__timeGroupAlias(timestamp, $__interval, 0)
  from spotify_streams where $__timeFilter(timestamp)
  group by time, platform
  order by time;

-- Complete listen counts for owned tracks
with tracks as
  (select distinct on (ss.track_uri) ss.track_uri, owr.id
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join owned_recordings owr on owr.recording_id = mr.musicbrainz_id)
  select sum(c) as "Total",
      avg(c) as "Mean",
      percentile_cont(0.5) within group (order by c) as "Median",
      mode() within group (order by c) as "Mode"
    from
      (select ss.track_uri, count(*) as c from spotify_streams ss
        join tracks on ss.track_uri = tracks.track_uri
        where $__timeFilter(timestamp) and reason_end = 'trackdone'
        group by ss.track_uri);

-- Top 10 completely streamed tracks
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Complete streams" desc, "Incomplete streams" desc
  limit 10;

-- Top 20 completely streamed unowned tracks
with tracks as
  (select distinct on (ss.track_uri) ss.track_uri, owr.id
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join owned_recordings owr on owr.recording_id = mr.musicbrainz_id)
  select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    track_name
    from spotify_streams ss
    left join tracks on ss.track_uri = tracks.track_uri
    where $__timeFilter(timestamp) and tracks.id is null
    group by ss.track_uri, track_name
  order by "Complete streams" desc, "Incomplete streams" desc
    limit 20;

-- Top 10 skipped tracks
select count(*) filter (where skipped = true
      or reason_end in ('backbtn', 'unknown', 'endplay', 'fwdbtn')) as "Skipped streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Skipped streams" desc, "Complete streams" desc
  limit 10;

-- Complete streams per track
select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Complete streams" desc, "Streams" desc;

-- Streams per track
select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Streams" desc, "Complete streams" desc;

-- Top 5 tracks over time, with others summed
with metrics as
  (select $__timeGroup(timestamp, $__interval) as time,
      track_name as metric,
      track_uri,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, track_uri, metric
    order by time asc, total desc)
  select time, metric, total from metrics where rank <= 5
  union all
  select time, 'Others', sum(total) from metrics where rank > 5
    group by time
    order by time asc;

-- Top 10 most streamed artists
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    sa.name
  from spotify_streams ss
  join spotify_tracks st on ss.track_uri = st.spotify_uri
  join spotify_track_artists sta on sta.track_id = st.spotify_id
  join spotify_artists sa on sa.spotify_id = sta.artist_id
  where $__timeFilter(timestamp)
  group by sa.spotify_id, sa.name
  order by "Complete streams" desc
  limit 10;

-- Complete album listens by type
with complete_albums as
  (select name, album_id, album_type, total_tracks from
    (select name, album_id, album_type, total_tracks, count(*) as tracks
      from
        (select distinct on (track_uri) name, album_id, total_tracks, album_type
          from spotify_streams ss
          join spotify_tracks st on st.spotify_uri = ss.track_uri
          join spotify_albums sa on sa.spotify_id = st.album_id
          where $__timeFilter(timestamp) and reason_end = 'trackdone')
      group by album_id, name, album_type, total_tracks)
    where tracks = total_tracks
    order by total_tracks desc)
  select album_type, count(*)
    from complete_albums
    group by album_type;

-- Top 10 albums
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    sa.name
  from spotify_streams ss
  join spotify_tracks st on ss.track_uri = st.spotify_uri
  join spotify_albums sa on sa.spotify_id = st.album_id
  where $__timeFilter(timestamp)
  group by sa.spotify_id, sa.name
  order by "Complete streams" desc
  limit 10;

-- Top 20 unowned albums
with tracks as
  (select distinct on (ss.track_uri) ss.track_uri, owr.id
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join owned_recordings owr on owr.recording_id = mr.musicbrainz_id)
  select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
      count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
      sa.name
    from spotify_streams ss
    join spotify_tracks st on ss.track_uri = st.spotify_uri
    join spotify_albums sa on sa.spotify_id = st.album_id
    left join tracks on ss.track_uri = tracks.track_uri
    where $__timeFilter(timestamp) and tracks.id is null
    group by sa.spotify_id, sa.name
    order by "Complete streams" desc
    limit 20;

-- Top 5 albums over time, with others summed
with metrics as
  (select $__timeGroup(timestamp, $__interval) as time,
      sa.name as metric,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams ss
    join spotify_tracks st on ss.track_uri = st.spotify_uri
    join spotify_albums sa on sa.spotify_id = st.album_id
    where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, sa.spotify_id, metric
    order by time asc, total desc)
  select time, metric, total from metrics where rank <= 5
  union all
  select time, 'Others', sum(total) from metrics where rank > 5
    group by time
    order by time asc;

-- Top 5 artists over time, with others summed
with metrics as
  (select $__timeGroup(timestamp, $__interval) as time,
      sa.name as metric,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams ss
    join spotify_tracks st on ss.track_uri = st.spotify_uri
    join spotify_track_artists sta on sta.track_id = st.spotify_id
    join spotify_artists sa on sa.spotify_id = sta.artist_id
    where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, sa.spotify_id, metric
    order by time asc, total desc)
  select time, metric, total from metrics where rank <= 5
  union all
  select time, 'Others', sum(total) from metrics where rank > 5
    group by time
    order by time asc;

-- Top 5 genres over time, with others summed
with metrics as
  (select $__timeGroup(timestamp, $__interval) as time,
      name as metric,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams ss
    join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
    join musicbrainz_recording_tags mrt on mrt.recording_id = mr.musicbrainz_id
    where $__timeFilter(timestamp) and reason_end = 'trackdone' and musicbrainz_genre_id is not null
    group by time, metric
    order by time asc, total desc)
  select time, metric, total from metrics where rank <= 5
  union all
  select time, 'Others', sum(total) from metrics where rank > 5
    group by time
    order by time asc;

-- Track popularity by time played
select popularity::text, sum(ms_played) as value
  from spotify_streams ss
  join spotify_tracks st on ss.track_uri = st.spotify_uri
  where $__timeFilter(timestamp)
  group by popularity
  order by popularity::integer asc;

-- Streams per album type
select album_type, count(*), $__timeGroupAlias(timestamp, $__interval, 0)
  from spotify_streams ss
  join spotify_tracks st on ss.track_uri = st.spotify_uri
  join spotify_albums sa on st.album_id = sa.spotify_id
  where $__timeFilter(timestamp)
  group by time, album_type
  order by time;

-- Percentage of tracks with various acoustic properties over time, of the tracks that have acoustic metadata.
select
  count(*) filter (where is_danceable) / count(*)::decimal as danceable,
  count(*) filter (where is_acoustic) / count(*)::decimal as acoustic,
  count(*) filter (where is_aggressive) / count(*)::decimal as aggressive,
  count(*) filter (where is_electronic) / count(*)::decimal as electronic,
  count(*) filter (where is_happy) / count(*)::decimal as happy,
  count(*) filter (where is_party) / count(*)::decimal as party,
  count(*) filter (where is_relaxed) / count(*)::decimal as relaxed,
  count(*) filter (where is_sad) / count(*)::decimal as sad,
  count(*) filter (where is_tonal) / count(*)::decimal as tonal,
  count(*) filter (where is_instrumental) / count(*)::decimal as instrumental
from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone';

-- Stream and track counts by BPM
select bpm::text, count(*) as "stream count", count(distinct track_uri) as "track count"
  from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone'
  group by bpm
  order by bpm::integer asc;

-- Key and scale
select key_key || ' ' || key_scale, count(*)
  from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone'
  group by key_key, key_scale;

-- Chord key and scale
select chords_key || ' ' || chords_scale, count(*)
  from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone'
  group by chords_key, chords_scale;

-- Vocal gender
select gender, count(*)
  from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone'
  group by gender;

-- Timbre
select timbre, count(*)
  from spotify_streams ss
  join musicbrainz_recordings mr on mr.spotify_uri = ss.track_uri
  join acousticbrainz a on a.recording_id = mr.musicbrainz_id
  where $__timeFilter(timestamp) and reason_end = 'trackdone'
  group by timbre;
