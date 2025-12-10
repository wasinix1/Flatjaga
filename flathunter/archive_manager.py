"""Archive manager for contacted listings - extracts and stores listing data"""
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from flathunter.logger_config import logger


class ArchiveManager:
    """Manages extraction and storage of contacted listing archives"""

    def __init__(self, config=None):
        """
        Initialize archive manager

        Args:
            config: YamlConfig instance (optional)
        """
        self.config = config

        # Local backup path (optional)
        if config:
            archive_path = config.get('telegram_archive_path', '~/.flathunter_archives')
        else:
            archive_path = '~/.flathunter_archives'

        self.archive_path = Path(archive_path).expanduser()

        # Retention days
        if config:
            self.retention_days = config.get('telegram_archive_retention_days', 30)
        else:
            self.retention_days = 30

    def extract_archive_data(self, page_source: str, listing_url: str, expose: Dict) -> Optional[Dict]:
        """
        Extract images and description from listing page HTML

        Args:
            page_source: HTML source of the listing page
            listing_url: URL of the listing
            expose: Expose dict with listing metadata

        Returns:
            Dict with keys: images (list), description (str), metadata (dict)
            Returns None if extraction fails completely
        """
        try:
            crawler = expose.get('crawler', '').lower()

            if 'willhaben' in crawler:
                return self._extract_willhaben(page_source, listing_url, expose)
            elif 'wg-gesucht' in crawler or 'wggesucht' in crawler:
                return self._extract_wggesucht(page_source, listing_url, expose)
            else:
                logger.warning(f"Unknown crawler type for archiving: {crawler}")
                return None

        except Exception as e:
            logger.error(f"Failed to extract archive data: {e}", exc_info=True)
            return None

    def _extract_willhaben(self, page_source: str, listing_url: str, expose: Dict) -> Optional[Dict]:
        """Extract archive data from Willhaben listing"""
        try:
            soup = BeautifulSoup(page_source, 'html.parser')

            # Extract images - multiple strategies
            images = []

            # Strategy 1: Find carousel images with data-testid
            img_elements = soup.find_all('img', {'data-testid': re.compile(r'image-\d+')})
            for img in img_elements:
                src = img.get('src', '')
                if src and src.startswith('http'):
                    images.append(src)

            # Strategy 2: Find images in carousel cells
            if not images:
                carousel_imgs = soup.find_all('img', class_=re.compile(r'(carousel|gallery)', re.I))
                for img in carousel_imgs:
                    src = img.get('src', '')
                    if src and src.startswith('http'):
                        images.append(src)

            # Strategy 3: All images in page (filter by URL pattern)
            if not images:
                all_imgs = soup.find_all('img')
                for img in all_imgs:
                    src = img.get('src', '')
                    # Willhaben images typically from cache.willhaben.at
                    if 'cache.willhaben.at' in src or 'willhaben.at/mmo' in src:
                        images.append(src)

            # Remove duplicates while preserving order
            seen = set()
            images = [x for x in images if not (x in seen or seen.add(x))]

            logger.info(f"Extracted {len(images)} images from Willhaben listing")

            # Extract description
            description = ""
            desc_div = soup.find('div', {'data-testid': 'ad-description-Objektbeschreibung'})
            if desc_div:
                description = desc_div.get_text(separator='\n', strip=True)
                logger.info(f"Extracted description ({len(description)} chars)")
            else:
                logger.warning("Could not find description div in Willhaben page")

            # Build metadata
            metadata = {
                'url': listing_url,
                'title': expose.get('title', 'N/A'),
                'price': expose.get('price', 'N/A'),
                'size': expose.get('size', 'N/A'),
                'rooms': expose.get('rooms', 'N/A'),
                'address': expose.get('address', 'N/A'),
                'crawler': expose.get('crawler', 'N/A'),
                'timestamp': datetime.now().isoformat(),
            }

            return {
                'images': images,
                'description': description,
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Failed to extract Willhaben archive data: {e}", exc_info=True)
            return None

    def _extract_wggesucht(self, page_source: str, listing_url: str, expose: Dict) -> Optional[Dict]:
        """Extract archive data from WG-Gesucht listing"""
        try:
            soup = BeautifulSoup(page_source, 'html.parser')

            # Extract images - WG-Gesucht specific (only apartment photos)
            images = []

            # Only extract sp-image class (apartment gallery photos)
            gallery_imgs = soup.find_all('img', class_='sp-image')
            for img in gallery_imgs:
                # Only use data-large for best quality
                src = img.get('data-large', '')

                # Filter out maps, icons, and other non-photo images
                if src and src.startswith('http') and '/media/up/' in src:
                    # Only apartment photos have /media/up/ in the URL
                    images.append(src)

            # Remove duplicates while preserving order
            seen = set()
            images = [x for x in images if not (x in seen or seen.add(x))]

            logger.info(f"Extracted {len(images)} apartment photos from WG-Gesucht listing")

            # Extract description - WG-Gesucht uses freitext divs with <p> tags
            description = ""

            # Strategy 1: Find freitext divs and extract all <p> tags
            freitext_divs = soup.find_all('div', class_=re.compile(r'section_freetext', re.I))
            if freitext_divs:
                desc_parts = []
                for div in freitext_divs:
                    # Get all <p> tags inside this div (ignore ads)
                    paragraphs = div.find_all('p', class_=lambda x: not x or 'ad' not in x.lower())
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 10:  # Filter out very short/empty paragraphs
                            desc_parts.append(text)

                if desc_parts:
                    description = '\n\n'.join(desc_parts)
                    logger.info(f"Extracted description ({len(description)} chars) from {len(desc_parts)} paragraphs")

            # Strategy 2: Fallback to freitext div text
            if not description:
                freitext_div = soup.find('div', id=re.compile(r'freitext', re.I))
                if freitext_div:
                    description = freitext_div.get_text(separator='\n', strip=True)
                    logger.info(f"Extracted description ({len(description)} chars) using fallback")

            # Strategy 3: Generic description container
            if not description:
                desc_div = soup.find('div', id='ad_description_text')
                if desc_div:
                    description = desc_div.get_text(separator='\n', strip=True)
                    logger.info(f"Extracted description ({len(description)} chars) from generic container")

            if not description:
                logger.warning("Could not find description in WG-Gesucht page")

            # Build metadata
            metadata = {
                'url': listing_url,
                'title': expose.get('title', 'N/A'),
                'price': expose.get('price', 'N/A'),
                'size': expose.get('size', 'N/A'),
                'rooms': expose.get('rooms', 'N/A'),
                'crawler': expose.get('crawler', 'N/A'),
                'timestamp': datetime.now().isoformat(),
            }

            return {
                'images': images,
                'description': description,
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Failed to extract WG-Gesucht archive data: {e}", exc_info=True)
            return None

    def save_archive_locally(self, archive_data: Dict, archive_id: str) -> bool:
        """
        Save archive data to local disk (optional backup)

        Args:
            archive_data: Dict with images, description, metadata
            archive_id: Unique identifier for this archive

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create archive directory
            archive_dir = self.archive_path / archive_id
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Save metadata
            metadata_file = archive_dir / 'metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(archive_data['metadata'], f, indent=2, ensure_ascii=False)

            # Save description
            if archive_data.get('description'):
                desc_file = archive_dir / 'description.txt'
                with open(desc_file, 'w', encoding='utf-8') as f:
                    f.write(archive_data['description'])

            # Save image URLs (not downloading actual images)
            if archive_data.get('images'):
                images_file = archive_dir / 'images.json'
                with open(images_file, 'w', encoding='utf-8') as f:
                    json.dump(archive_data['images'], f, indent=2)

            logger.info(f"Saved archive locally: {archive_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to save archive locally: {e}", exc_info=True)
            return False

    def cleanup_old_archives(self) -> int:
        """
        Clean up archives older than retention_days

        Returns:
            Number of archives deleted
        """
        try:
            if not self.archive_path.exists():
                return 0

            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            deleted_count = 0

            for archive_dir in self.archive_path.iterdir():
                if not archive_dir.is_dir():
                    continue

                # Check modification time
                mtime = datetime.fromtimestamp(archive_dir.stat().st_mtime)
                if mtime < cutoff_date:
                    try:
                        # Delete all files in directory
                        for file in archive_dir.iterdir():
                            file.unlink()
                        archive_dir.rmdir()
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete archive {archive_dir}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old archives")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old archives: {e}", exc_info=True)
            return 0
