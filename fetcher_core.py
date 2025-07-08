import yt_dlp
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import os
import time

def clean_query(query):
    query = re.sub(r"\([^)]*\)", "", query)
    query = re.sub(r"\[[^]]*\]", "", query)
    query = re.sub(r"-\s*(Remastered|Live|Edit|Version|Mono|Stereo|Explicit|Single Mix|Radio Edit).*", "", query, flags=re.IGNORECASE)
    return query.strip()

def alternate_queries(query):
    alternates = [query]
    cleaned = clean_query(query)
    if cleaned != query:
        alternates.append(cleaned)
    if ' - ' in cleaned:
        artist, track = cleaned.split(' - ', 1)
        alternates.append(f"{track} - {artist}")
    return list(dict.fromkeys(alternates))

def get_youtube_link(query):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'default_search': 'ytsearch1',
    }
    for alt_query in alternate_queries(query):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                result = ydl.extract_info(alt_query, download=False)
                if 'entries' in result and result['entries']:
                    return f"https://www.youtube.com/watch?v={result['entries'][0]['id']}"
            except Exception:
                continue
    return "FAILED"

def run_fetch(input_csv, output_csv, failed_csv, progress_callback, pause_event, stop_event, max_threads=3):
    try:
        df = pd.read_csv(input_csv, sep=None, engine="python")
    except Exception as e:
        progress_callback({'type': 'error', 'msg': f"Error reading input CSV: {e}"})
        return
    queries = [f"{r['Artist Name(s)']} - {r['Track Name']}" for _, r in df.iterrows()]
    existing = set()
    if os.path.exists(output_csv):
        try:
            out_df = pd.read_csv(output_csv)
            existing = set(out_df['query'])
        except Exception:
            pass
    results = []
    failed = []
    total = len(queries)
    completed = 0
    skipped = 0
    def log(msg):
        progress_callback({'type': 'log', 'msg': msg})
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_query = {}
        for q in queries:
            if stop_event.is_set():
                log('🛑 Stopped by user.')
                break
            if q in existing:
                skipped += 1
                progress_callback({'type': 'progress', 'completed': completed, 'skipped': skipped, 'failed': len(failed), 'total': total})
                log(f"✔️ Skipped: {q} already exists.")
                continue
            future = executor.submit(get_youtube_link, q)
            future_to_query[future] = q
        for i, future in enumerate(as_completed(future_to_query), 1):
            while pause_event.is_set():
                time.sleep(0.5)
            if stop_event.is_set():
                log('🛑 Stopped by user.')
                break
            query = future_to_query[future]
            url = future.result()
            results.append((query, url))
            completed += 1
            if url == "FAILED":
                failed.append(query)
            progress_callback({'type': 'progress', 'completed': completed, 'skipped': skipped, 'failed': len(failed), 'total': total})
            log(f"{completed}/{len(future_to_query)}: {query} -> {url}")
    # Append new results to output
    if results:
        new_df = pd.DataFrame(results, columns=["query", "url"])
        if os.path.exists(output_csv):
            new_df.to_csv(output_csv, mode='a', header=False, index=False)
        else:
            new_df.to_csv(output_csv, index=False)
    if failed:
        pd.DataFrame(failed, columns=["query"]).to_csv(failed_csv, index=False)
        log(f"❌ {len(failed)} queries failed. Saved to {failed_csv}")
    log(f"✅ Done. Links saved to {output_csv}") 