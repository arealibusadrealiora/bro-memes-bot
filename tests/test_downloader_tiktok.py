"""Tests for TikTok download functionality in MediaDownloader."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from bro_memes_bot.utils.downloader import MediaDownloader


@pytest.fixture
def downloader():
    """Create a MediaDownloader instance with mocked CobaltClient."""
    with patch('bro_memes_bot.utils.downloader.CobaltClient') as mock_cobalt:
        mock_client = MagicMock()
        mock_cobalt.return_value = mock_client
        downloader = MediaDownloader()
        downloader.cobalt_client = mock_client
        return downloader


class TestTikTokSlideshow:
    """Tests for TikTok slideshow/photo posts via Cobalt API."""

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_multiple_images(self, downloader):
        """Test downloading a TikTok slideshow with multiple images."""
        # Mock Cobalt API response for slideshow (picker status)
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/image1.jpg', 'type': 'photo'},
                {'url': 'https://example.com/image2.jpg', 'type': 'photo'},
                {'url': 'https://example.com/image3.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file downloads
        async def mock_fetch_file(url, filename):
            return f'/tmp/{filename}'

        downloader._fetch_file = AsyncMock(side_effect=mock_fetch_file)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 3
        assert result['files'][0] == '/tmp/tiktok_slideshow_0.jpg'
        assert result['files'][1] == '/tmp/tiktok_slideshow_1.jpg'
        assert result['files'][2] == '/tmp/tiktok_slideshow_2.jpg'
        assert result['title'] == 'TikTok slideshow'
        assert result['duration'] is None
        assert result['thumbnail'] is None
        assert result['uploader'] is None

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_single_image(self, downloader):
        """Test downloading a TikTok slideshow with only one image."""
        # Mock Cobalt API response for single image in picker
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/single.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download
        downloader._fetch_file = AsyncMock(return_value='/tmp/tiktok_slideshow_0.jpg')

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions - should return single file_path, not files array
        assert result is not None
        assert 'file_path' in result
        assert 'files' not in result
        assert result['file_path'] == '/tmp/tiktok_slideshow_0.jpg'
        assert result['title'] == 'TikTok post'

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_with_video_mixed(self, downloader):
        """Test downloading a TikTok slideshow with mixed photos and video."""
        # Mock Cobalt API response with mixed content
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/image1.jpg', 'type': 'photo'},
                {'url': 'https://example.com/video.mp4', 'type': 'video'},
                {'url': 'https://example.com/image2.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file downloads with correct extensions
        async def mock_fetch_file(url, filename):
            return f'/tmp/{filename}'

        downloader._fetch_file = AsyncMock(side_effect=mock_fetch_file)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 3
        assert result['files'][0] == '/tmp/tiktok_slideshow_0.jpg'
        assert result['files'][1] == '/tmp/tiktok_slideshow_1.mp4'  # Video in slideshow
        assert result['files'][2] == '/tmp/tiktok_slideshow_2.jpg'

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_empty_picker(self, downloader):
        """Test error handling when Cobalt returns empty picker."""
        # Mock Cobalt API response with empty picker
        mock_cobalt_response = {
            'status': 'picker',
            'picker': []
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions - should return None due to ValueError
        assert result is None

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_download_failure(self, downloader):
        """Test error handling when file download fails."""
        # Mock Cobalt API response
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/image1.jpg', 'type': 'photo'},
                {'url': 'https://example.com/image2.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download to fail (return None)
        downloader._fetch_file = AsyncMock(return_value=None)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions - should return None when no files downloaded
        assert result is None

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_partial_download_failure(self, downloader):
        """Test handling when some files fail to download."""
        # Mock Cobalt API response
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/image1.jpg', 'type': 'photo'},
                {'url': 'https://example.com/image2.jpg', 'type': 'photo'},
                {'url': 'https://example.com/image3.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download - first succeeds, second fails, third succeeds
        async def mock_fetch_file(url, filename):
            if 'image2' in url:
                return None
            return f'/tmp/{filename}'

        downloader._fetch_file = AsyncMock(side_effect=mock_fetch_file)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions - should return only successfully downloaded files
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 2
        assert result['files'][0] == '/tmp/tiktok_slideshow_0.jpg'
        assert result['files'][1] == '/tmp/tiktok_slideshow_2.jpg'

    @pytest.mark.asyncio
    async def test_tiktok_slideshow_missing_url_in_picker_item(self, downloader):
        """Test handling when picker items have missing URLs."""
        # Mock Cobalt API response with missing URL
        mock_cobalt_response = {
            'status': 'picker',
            'picker': [
                {'url': 'https://example.com/image1.jpg', 'type': 'photo'},
                {'type': 'photo'},  # Missing URL
                {'url': 'https://example.com/image2.jpg', 'type': 'photo'},
            ]
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file downloads
        async def mock_fetch_file(url, filename):
            return f'/tmp/{filename}'

        downloader._fetch_file = AsyncMock(side_effect=mock_fetch_file)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/photo/123')

        # Assertions - should skip item with missing URL
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 2
        assert result['files'][0] == '/tmp/tiktok_slideshow_0.jpg'
        assert result['files'][1] == '/tmp/tiktok_slideshow_2.jpg'


class TestTikTokSingleVideo:
    """Tests for TikTok single video posts via Cobalt API."""

    @pytest.mark.asyncio
    async def test_tiktok_single_video_redirect_status(self, downloader):
        """Test downloading a TikTok single video with redirect status."""
        # Mock Cobalt API response for single video
        mock_cobalt_response = {
            'status': 'redirect',
            'url': 'https://example.com/video.mp4',
            'filename': 'tiktok_video_123.mp4'
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download
        downloader._fetch_file = AsyncMock(return_value='/tmp/tiktok_video_123.mp4')

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions
        assert result is not None
        assert 'file_path' in result
        assert 'files' not in result
        assert result['file_path'] == '/tmp/tiktok_video_123.mp4'
        assert result['title'] == 'tiktok_video_123'
        assert result['duration'] is None

    @pytest.mark.asyncio
    async def test_tiktok_single_video_tunnel_status(self, downloader):
        """Test downloading a TikTok single video with tunnel status."""
        # Mock Cobalt API response with tunnel status
        mock_cobalt_response = {
            'status': 'tunnel',
            'url': 'https://example.com/video.mp4',
            'filename': 'tiktok_video_456.mp4'
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download
        downloader._fetch_file = AsyncMock(return_value='/tmp/tiktok_video_456.mp4')

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/456')

        # Assertions
        assert result is not None
        assert result['file_path'] == '/tmp/tiktok_video_456.mp4'

    @pytest.mark.asyncio
    async def test_tiktok_single_video_missing_url(self, downloader):
        """Test error handling when Cobalt response missing URL."""
        # Mock Cobalt API response with missing URL
        mock_cobalt_response = {
            'status': 'redirect',
            'filename': 'tiktok_video.mp4'
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions - should return None due to ValueError
        assert result is None

    @pytest.mark.asyncio
    async def test_tiktok_single_video_download_failure(self, downloader):
        """Test error handling when file download fails."""
        # Mock Cobalt API response
        mock_cobalt_response = {
            'status': 'redirect',
            'url': 'https://example.com/video.mp4',
            'filename': 'tiktok_video.mp4'
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Mock file download to fail
        downloader._fetch_file = AsyncMock(return_value=None)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions
        assert result is None


class TestTikTokErrorHandling:
    """Tests for TikTok error handling."""

    @pytest.mark.asyncio
    async def test_tiktok_cobalt_api_failure(self, downloader):
        """Test error handling when Cobalt API fails."""
        # Mock Cobalt API to return None
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=None)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions
        assert result is None

    @pytest.mark.asyncio
    async def test_tiktok_unexpected_status(self, downloader):
        """Test error handling for unexpected Cobalt status."""
        # Mock Cobalt API response with unexpected status
        mock_cobalt_response = {
            'status': 'unknown_status',
            'data': 'something'
        }
        downloader.cobalt_client.get_media_info = AsyncMock(return_value=mock_cobalt_response)

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions
        assert result is None

    @pytest.mark.asyncio
    async def test_tiktok_cobalt_exception(self, downloader):
        """Test error handling when Cobalt client raises exception."""
        # Mock Cobalt API to raise exception
        downloader.cobalt_client.get_media_info = AsyncMock(side_effect=Exception("Network error"))

        # Test
        result = await downloader._download_tiktok_via_cobalt('https://tiktok.com/@user/video/123')

        # Assertions
        assert result is None
