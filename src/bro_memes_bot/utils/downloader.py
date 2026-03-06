import os
import tempfile
from pathlib import Path
import yt_dlp
from typing import Optional, Dict, List
import logging
import httpx
from .cobalt_client import CobaltClient
import re

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

class MediaDownloader:
    """Handles media downloads from various platforms using yt-dlp"""
    
    # Constants
    MAX_FILE_SIZE = 50_000_000  # 50MB Telegram limit
    MAX_TITLE_LENGTH = 64
    
    def __init__(self):
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': str(Path(tempfile.gettempdir()) / '%(extractor)s_%(id)s.%(ext)s'),
            'max_filesize': self.MAX_FILE_SIZE,
        }
        
        # Combine options to reduce duplication
        self.yt_opts = {
            **self.base_opts,
            'netrc_location': os.getenv('NETRC_LOCATION'),
            'cachedir': os.getenv('CACHE_DIR'),
            'usenetrc': True,
        }
        
        self.cobalt_client = CobaltClient(
            base_url=os.getenv('COBALT_BASE_URL', 'http://localhost:9000/'),
            api_key=os.getenv('COBALT_API_KEY')
        )
    
    def _sanitize_title(self, title: str) -> str:
        """Sanitize and truncate title"""
        # Remove non-word characters except basic punctuation
        clean_title = re.sub(r'[^\w\s,.!?-]', '', title)
        # Replace multiple spaces with single space
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        return clean_title[:self.MAX_TITLE_LENGTH] if clean_title else 'media'

    async def _fetch_file(self, url: str, filename: str) -> Optional[str]:
        """Download a file from a direct URL, return local path or None."""
        try:
            temp_file = Path(tempfile.gettempdir()) / filename
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.get(url)
                response.raise_for_status()
                temp_file.write_bytes(response.content)
            return str(temp_file)
        except Exception as e:
            logger.error(f"Error fetching file {filename}: {str(e)}")
            return None

    async def _download_with_ytdl(self, url: str, opts: Dict) -> Optional[Dict]:
        """Generic yt-dlp download handler"""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Check file size first
                info = ydl.extract_info(url, download=False)
                if info.get('filesize', 0) > self.MAX_FILE_SIZE:
                    raise ValueError("Video file is too large (>50MB)")
                
                # Download if size check passes
                info = ydl.extract_info(url, download=True)
                
                return {
                    'file_path': ydl.prepare_filename(info),
                    'title': self._sanitize_title(info.get('title', 'video')),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader'),
                }
                
        except Exception as e:
            logger.error(f"Error downloading from {url}: {str(e)}")
            return None

    async def _download_tiktok_via_cobalt(self, url: str) -> Optional[Dict]:
        """
        Fallback for TikTok photo/slideshow posts that yt-dlp cannot handle.
        Uses Cobalt API, which supports /photo/ URLs and returns a picker for slideshows.
        """
        try:
            data = await self.cobalt_client.get_media_info(url)
            if not data:
                raise ValueError("Cobalt returned no data")

            status = data.get('status', '')

            # Slideshow / carousel
            if status == 'picker':
                items = data.get('picker', [])
                if not items:
                    raise ValueError("Cobalt picker is empty")

                downloaded: List[str] = []
                for i, item in enumerate(items):
                    item_url = item.get('url')
                    if not item_url:
                        continue
                    ext = 'mp4' if item.get('type') == 'video' else 'jpg'
                    fp = await self._fetch_file(item_url, f'tiktok_slide_{i}.{ext}')
                    if fp:
                        downloaded.append(fp)

                if not downloaded:
                    raise ValueError("Failed to download any slideshow items")

                if len(downloaded) == 1:
                    return {
                        'file_path': downloaded[0],
                        'title': 'TikTok post',
                        'duration': None, 'thumbnail': None, 'uploader': None,
                    }
                return {
                    'files': downloaded,
                    'title': 'TikTok slideshow',
                    'duration': None, 'thumbnail': None, 'uploader': None,
                }

            # Single video via Cobalt
            if status in ('redirect', 'tunnel'):
                single_url = data.get('url')
                if not single_url:
                    raise ValueError("Cobalt response missing URL")
                filename = data.get('filename', 'tiktok_video.mp4')
                fp = await self._fetch_file(single_url, filename)
                if not fp:
                    raise ValueError("Failed to download file")
                return {
                    'file_path': fp,
                    'title': self._sanitize_title(Path(filename).stem),
                    'duration': None, 'thumbnail': None, 'uploader': None,
                }

            raise ValueError(f"Unexpected Cobalt status: {status}")

        except Exception as e:
            logger.error(f"Error downloading TikTok via Cobalt: {str(e)}")
            return None        

    async def _download_tiktok_slideshow(self, url: str) -> Optional[Dict]:
        """Fallback for TikTok image slideshows."""
        try:
            out_template = str(
                Path(tempfile.gettempdir()) / 'tiktok_%(id)s_%(autonumber)s.%(ext)s'
            )
            opts = {**self.base_opts, 'outtmpl': out_template, 'format': 'best'}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                post_id = info.get('id', '')
                tmp = Path(tempfile.gettempdir())
                files = (
                    sorted(tmp.glob(f'tiktok_{post_id}_*.jpg')) +
                    sorted(tmp.glob(f'tiktok_{post_id}_*.png')) +
                    sorted(tmp.glob(f'tiktok_{post_id}_*.webp')) +
                    sorted(tmp.glob(f'tiktok_{post_id}_*.mp4'))
                )
                if not files:
                    return None
                base = {
                    'title': self._sanitize_title(info.get('title', 'tiktok')),
                    'uploader': info.get('uploader'),
                    'thumbnail': info.get('thumbnail'),
                }
                if len(files) == 1:
                    return {**base, 'file_path': str(files[0]), 'duration': info.get('duration')}
                return {**base, 'files': [str(f) for f in files], 'duration': None}
        except Exception as e:
            logger.error(f"Error downloading TikTok slideshow: {str(e)}")
            return None

    async def download_youtube(self, url: str) -> Optional[Dict]:
        """Download YouTube Shorts"""
        if '/shorts/' not in url:
            logger.info("Not a YouTube Shorts URL, skipping download")
            return None
        return await self._download_with_ytdl(url, self.yt_opts)
            
    async def download_tiktok(self, url: str) -> Optional[Dict]:
        result = await self._download_with_ytdl(url, self.base_opts)
        if result and Path(result['file_path']).exists():
            return result
        # yt-dlp cannot handle /photo/ posts — fall back to Cobalt
        logger.info("Standard TikTok download failed, trying Cobalt fallback")
        return await self._download_tiktok_via_cobalt(url)

    async def download_twitter(self, url: str) -> Optional[Dict]:
        """Download Twitter/X video"""
        result = await self._download_with_ytdl(url, self.base_opts)
        if result:
            title = result.get('title', '')
            if not title or title == 'Twitter':
                uploader = result.get('uploader', 'unknown')
                result['title'] = self._sanitize_title(f"Twitter_video_by_{uploader}")
        return result

    async def download_instagram(self, url: str) -> Optional[Dict]:
        """
        Download Instagram media via Cobalt API.
        Returns either:
          {'file_path': str, ...}            — single video or image
          {'files': [str, str, ...], ...}    — carousel
        """
        try:
            data = await self.cobalt_client.get_media_info(url)
            if not data:
                raise ValueError("Failed to get media info from Cobalt API")

            status = data.get('status', '')

            # Carousel
            if status == 'picker':
                items = data.get('picker', [])
                if not items:
                    raise ValueError("Cobalt returned picker with no items")

                downloaded: List[str] = []
                for i, item in enumerate(items):
                    item_url = item.get('url')
                    if not item_url:
                        continue
                    ext = 'mp4' if item.get('type') == 'video' else 'jpg'
                    fp = await self._fetch_file(item_url, f'instagram_carousel_{i}.{ext}')
                    if fp:
                        downloaded.append(fp)

                if not downloaded:
                    raise ValueError("Failed to download any carousel items")

                if len(downloaded) == 1:
                    return {
                        'file_path': downloaded[0],
                        'title': 'Instagram post',
                        'duration': None, 'thumbnail': None, 'uploader': None,
                    }
                return {
                    'files': downloaded,
                    'title': 'Instagram carousel',
                    'duration': None, 'thumbnail': None, 'uploader': None,
                }

            # Single file
            if status in ('redirect', 'tunnel'):
                single_url = data.get('url')
                if not single_url:
                    raise ValueError("Cobalt response missing URL")
                filename = data.get('filename', 'instagram_media')
                fp = await self._fetch_file(single_url, filename)
                if not fp:
                    raise ValueError("Failed to download media file")
                return {
                    'file_path': fp,
                    'title': self._sanitize_title(Path(filename).stem),
                    'duration': None, 'thumbnail': None, 'uploader': None,
                }

            raise ValueError(f"Unexpected Cobalt status: {status}")

        except Exception as e:
            logger.error(f"Error downloading Instagram media: {str(e)}")
            return None

    def cleanup(self, file_path: str) -> None:
        """Remove downloaded file"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.error(f"Error cleaning up file {file_path}: {str(e)}")
            
    def cleanup_files(self, file_paths: List[str]) -> None:
        for fp in file_paths:
            self.cleanup(fp)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cobalt_client.close()