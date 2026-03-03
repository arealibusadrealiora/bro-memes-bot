import os
import httpx
import logging
from typing import Optional, Dict, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parents[3] / '.env'
load_dotenv(env_path)

logger = logging.getLogger(__name__)

class CobaltClient:
    """Client for Cobalt API (https://cobalt.tools/)"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("COBALT_API_KEY environment variable is not set")
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client"""
        if self._client is None:
            self._client = httpx.AsyncClient(headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Api-Key {self.api_key}'
            })
        return self._client
    
    async def close(self):
        """Close the client session"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def get_media_info(self, url: str) -> Optional[Dict]:
        """
        Get raw Cobalt API response for a URL.
        Possible response shapes:
          {"status": "redirect"|"tunnel", "url": "...", "filename": "..."}
          {"status": "picker", "picker": [{"type": "photo"|"video", "url": "..."}], "filename": "..."}
          {"status": "error", "error": {"code": "...", "context": ...}}
        """
        try:
            client = await self._get_client()
            payload = {
                'url': url,
                # 'videoQuality': video_quality,
                # 'filenameStyle': 'pretty',  # More readable filenames
                'downloadMode': 'auto',     # Download both video and audio
            }
            response = await client.post(self.base_url, json=payload)
            logger.info(f"Cobalt API response: {response.text}")
            logger.info(f"Cobalt API response headers: {response.headers}")
            logger.info(response)
            response.raise_for_status()
            data = response.json()

            if data.get('status') == 'error':
                error = data.get('error', {})
                logger.error(
                    f"Cobalt API error: {error.get('code')} "
                    f"Context: {error.get('context')}"
                )
                return None

            return data

        except httpx.RequestError as e:
            logger.error(f"Error making request to Cobalt API: {str(e)}")
            return None
        except KeyError as e:
            logger.error(f"Unexpected Cobalt API response format: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while getting media URL: {str(e)}")
            return None