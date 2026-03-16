import yt_dlp
import asyncio
from functools import partial
import os
from typing import Any

def extract_video_info(url: str):
    """
    Extracts video information and available formats synchronously.
    Returns a dictionary of useful formats or None if failed.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False, # We need the details
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Filter formats
            # We want simple video+audio formats (like 360p, 720p) and maybe audio only.
            # Avoid downloading dash video only (which requires ffmpeg merging) if we can help it for simplicity, 
            # though yt-dlp with ffmpeg does it automatically. We'll simplify the UI by choosing pre-merged formats
            # or best video+audio.
            
            formats_list = []
            
            # Look for bestaudio
            formats_list.append({
                'format_id': 'bestaudio',
                'resolution': 'صوت فقط (Audio)',
                'ext': 'mp3'
            })
            
            # Grab some common resolutions (if available as single files usually mp4 with acodec)
            # Or we just rely on yt-dlp to merge them.
            available_heights = set()
            for f in info.get('formats', []):
                # Filter out those without video
                if f.get('vcodec') != 'none' and f.get('height'):
                    available_heights.add(f['height'])
            
            # Sort heights (e.g. 144, 360, 480, 720, 1080)
            sorted_heights = sorted(list(available_heights))
            
            # Let's provide an option for the best available
            formats_list.append({
                'format_id': 'best',
                'resolution': 'أفضل جودة (Best)',
                'ext': 'mp4'
            })
            
            # Let's add a few specific ones if they exist
            target_resolutions = [360, 480, 720, 1080]
            for res in target_resolutions:
                if res in sorted_heights:
                    formats_list.append({
                        'format_id': f'bestvideo[height<={res}]+bestaudio/best[height<={res}]',
                        'resolution': f'{res}p',
                        'ext': 'mp4'
                    })
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats_list
            }
            
    except Exception as e:
        print(f"Error extracting info: {e}")
        return None

async def download_video(url: str, format_id: str, output_path: str = "downloads"):
    """
    Downloads the video asynchronously using asyncio and run_in_executor.
    Returns the path to the downloaded file.
    """
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    
    # Configure yt-dlp options based on selected format
    ydl_opts: dict[str, Any] = {
        'format': format_id,
        'outtmpl': f'{output_path}/%(title)s_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4' if 'video' in format_id or 'best' in format_id else None,
    }
    
    if format_id == 'bestaudio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        ydl_opts['outtmpl'] = f'{output_path}/%(title)s_%(id)s.%(ext)s'
    
    def _download(*args: Any, **kwargs: Any) -> str | None:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                # Ensure the correct extension is used in the filename return
                filename = ydl.prepare_filename(info_dict)
                
                # If audio, yt-dlp post-processor changes extension
                if format_id == 'bestaudio':
                    base, ext = os.path.splitext(filename)
                    if ext != '.mp3':
                        filename = base + '.mp3'
                        
                return filename
        except Exception as e:
            print(f"Download error: {e}")
            return None

    # Run blocking yt-dlp call in a separate thread
    loop = asyncio.get_event_loop()
    filename = await loop.run_in_executor(None, _download)
    
    return filename
