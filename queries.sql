-- These queries use the $__timeFilter, $__timeGroup and $__timeGroupAlias Grafana macros and the $__interval Grafana variable. $__interval should be set to produce up to about 12 data points, or the graphs will be too busy to be readable.

-- Stream counts for gauge visualisation
select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Completed streams",
    count(distinct track_uri) "Tracks",
    count(distinct artist_name) "Artists",
    count(distinct album_name) "Albums"
  from spotify_streams where $__timeFilter(timestamp);

-- Total and average stream lengths
select sum(ms_played) "Total",
    avg(ms_played) as "Average stream length",
    avg(ms_played) filter (where reason_end = 'trackdone') as "Average complete stream length"
  from spotify_streams where $__timeFilter(timestamp);

-- Time streamed
select sum(ms_played), $__timeGroupAlias(timestamp, $__interval, 0)
  from spotify_streams where $__timeFilter(timestamp) group by time;

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
    order by day, hour)

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
  order by time

-- Top 10 completely streamed tracks
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Complete streams" desc, "Incomplete streams" desc
  limit 10

-- Top 10 skipped tracks
select count(*) filter (where skipped = true) as "Skipped streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Skipped streams" desc, "Complete streams" desc
  limit 10

-- Top 10 incompletely streamed tracks
select count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Incomplete streams" desc, "Complete streams" desc
  limit 10

-- Complete streams per track
select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Complete streams" desc, "Streams" desc

-- Streams per track
select count(*) as "Streams",
    count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    track_name,
    track_uri
  from spotify_streams where $__timeFilter(timestamp)
  group by track_uri, track_name
  order by "Streams" desc, "Complete streams" desc

-- Top 5 tracks
select time, metric, total
  from (select $__timeGroup(timestamp, $__interval) as time,
      track_name as metric,
      track_uri,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, track_uri, metric
    order by time asc, total desc)
  where rank <= 5

-- Top 10 most streamed artists
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    artist_name
  from spotify_streams where $__timeFilter(timestamp)
  group by artist_name
  order by "Complete streams" desc
  limit 10

-- Top 10 albums
select count(*) filter (where reason_end = 'trackdone') as "Complete streams",
    count(*) filter (where reason_end <> 'trackdone') as "Incomplete streams",
    album_name
  from spotify_streams where $__timeFilter(timestamp)
  group by album_name
  order by "Complete streams" desc
  limit 10

-- Top 5 albums
select time, metric, total
  from (select $__timeGroup(timestamp, $__interval) as time,
      album_name as metric,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, metric
    order by time asc, total desc)
  where rank <= 5

-- Top 5 artists
select time, metric, total
  from (select $__timeGroup(timestamp, $__interval) as time,
      artist_name as metric,
      count(*) as total,
      dense_rank() over (partition by $__timeGroup(timestamp, $__interval) order by count(*) desc) as rank
    from spotify_streams where $__timeFilter(timestamp) and reason_end = 'trackdone'
    group by time, metric
    order by time asc, total desc)
  where rank <= 5
