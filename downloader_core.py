import yt_dlp
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_DOWNLOAD_THREADS = 6

def _download_single(url, output_dir, audio_format):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_audio(urls, output_dir, progress_callback, pause_event, stop_event, audio_format='mp3'):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    total = len(urls)
    completed = 0
    failed = 0
    results = []
    def log(msg):
        progress_callback({'type': 'log', 'msg': msg})
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_THREADS) as executor:
        future_to_url = {executor.submit(_download_single, url, output_dir, audio_format): url for url in urls}
        for i, future in enumerate(as_completed(future_to_url), 1):
            url = future_to_url[future]
            if stop_event.is_set():
                log('🛑 Download stopped by user.')
                break
            while pause_event.is_set():
                time.sleep(0.5)
            try:
                future.result()
                completed += 1
                log(f'⬇️ Downloaded {url} ({i}/{total})')
            except Exception as e:
                failed += 1
                log(f'❌ Failed to download {url}: {e}')
            progress_callback({'type': 'progress', 'completed': completed, 'failed': failed, 'total': total})
    log(f'✅ Download complete. {completed} succeeded, {failed} failed.') 