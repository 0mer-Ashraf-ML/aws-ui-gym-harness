"""
Tab Visualizer - Generate visual screenshots of browser tabs for AI models
"""

import io
import logging
from typing import Dict, List
from PIL import Image, ImageDraw, ImageFont


class TabVisualizer:
    """Generate visual representations of browser tabs"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_tab_screenshot(self, tab_info: Dict) -> bytes:
        """
        Generate a visual screenshot showing all open tabs
        
        Args:
            tab_info: Dictionary with tab_count, current_tab_index, and tabs list
            
        Returns:
            PNG image as bytes
        """
        try:
            # Extract tab data
            tabs = tab_info.get('tabs', [])
            current_idx = tab_info.get('current_tab_index', -1)
            tab_count = tab_info.get('tab_count', len(tabs))
            
            if not tabs:
                return self._generate_empty_tabs_image()
            
            # Image dimensions
            width = 1200
            header_height = 100
            tab_card_height = 120
            tab_spacing = 20
            cards_per_row = 2
            rows = (len(tabs) + cards_per_row - 1) // cards_per_row
            content_height = rows * (tab_card_height + tab_spacing) + tab_spacing
            height = header_height + content_height + 40
            
            # Create image
            img = Image.new('RGB', (width, height), color='#1e1e1e')
            draw = ImageDraw.Draw(img)
            
            # Try to load fonts, fall back to default if not available
            try:
                title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
                heading_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
                label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
                url_font = ImageFont.truetype("/System/Library/Fonts/Courier.ttc", 14)
            except:
                # Fallback to default font
                title_font = ImageFont.load_default()
                heading_font = ImageFont.load_default()
                label_font = ImageFont.load_default()
                url_font = ImageFont.load_default()
            
            # Draw header
            self._draw_header(draw, width, header_height, tab_count, title_font, label_font)
            
            # Draw tab cards
            y_offset = header_height + tab_spacing
            for i, tab in enumerate(tabs):
                row = i // cards_per_row
                col = i % cards_per_row
                
                x = 20 + col * (width - 40) // cards_per_row + (col * tab_spacing)
                y = y_offset + row * (tab_card_height + tab_spacing)
                card_width = (width - 40 - tab_spacing) // cards_per_row
                
                is_current = tab.get('is_current', False) or tab.get('index', -1) == current_idx
                
                self._draw_tab_card(
                    draw, 
                    x, y, 
                    card_width, 
                    tab_card_height,
                    tab, 
                    is_current,
                    heading_font,
                    label_font,
                    url_font
                )
            
            # Convert to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            self.logger.info(f"✅ Generated tab visualization: {tab_count} tabs, {width}x{height}px")
            return img_bytes.getvalue()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to generate tab screenshot: {e}")
            return self._generate_error_image(str(e))
    
    def _draw_header(self, draw, width, height, tab_count, title_font, label_font):
        """Draw the header section"""
        # Background
        draw.rectangle([0, 0, width, height], fill='#2d2d2d')
        
        # Title
        title = "🗂️ Browser Tabs"
        draw.text((30, 25), title, fill='#ffffff', font=title_font)
        
        # Tab count badge
        badge_text = f"{tab_count} tab{'s' if tab_count != 1 else ''}"
        badge_x = width - 180
        badge_y = 30
        badge_width = 150
        badge_height = 40
        
        # Badge background
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_width, badge_y + badge_height],
            radius=20,
            fill='#1976d2'
        )
        
        # Badge text (centered)
        bbox = draw.textbbox((0, 0), badge_text, font=label_font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = badge_x + (badge_width - text_width) // 2
        text_y = badge_y + (badge_height - text_height) // 2 - 2
        draw.text((text_x, text_y), badge_text, fill='#ffffff', font=label_font)
        
        # Bottom border
        draw.line([0, height, width, height], fill='#444444', width=2)
    
    def _draw_tab_card(self, draw, x, y, width, height, tab, is_current, heading_font, label_font, url_font):
        """Draw a single tab card"""
        # Card background
        bg_color = '#1565c0' if is_current else '#2d2d2d'
        border_color = '#1976d2' if is_current else '#444444'
        border_width = 3 if is_current else 1
        
        # Draw card
        draw.rounded_rectangle(
            [x, y, x + width, y + height],
            radius=8,
            fill=bg_color,
            outline=border_color,
            width=border_width
        )
        
        # Tab index badge
        tab_idx = tab.get('index', -1)
        badge_text = f"Tab {tab_idx + 1}"
        badge_x = x + 10
        badge_y = y + 10
        badge_width = 70
        badge_height = 25
        
        badge_bg = '#ffffff' if is_current else '#1976d2'
        badge_fg = '#000000' if is_current else '#ffffff'
        
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_width, badge_y + badge_height],
            radius=12,
            fill=badge_bg
        )
        
        bbox = draw.textbbox((0, 0), badge_text, font=label_font)
        text_width = bbox[2] - bbox[0]
        text_x = badge_x + (badge_width - text_width) // 2
        draw.text((text_x, badge_y + 5), badge_text, fill=badge_fg, font=label_font)
        
        # Current indicator
        if is_current:
            current_text = "✓ CURRENT"
            current_x = x + width - 100
            draw.text((current_x, badge_y + 5), current_text, fill='#4caf50', font=label_font)
        
        # URL hostname (bold)
        url = tab.get('url', 'about:blank')
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname or url
        except:
            hostname = url[:30]
        
        text_color = '#ffffff'
        hostname_y = y + 45
        # Truncate if too long
        if len(hostname) > 40:
            hostname = hostname[:37] + "..."
        draw.text((x + 15, hostname_y), hostname, fill=text_color, font=heading_font)
        
        # Full URL (smaller, monospace)
        url_y = y + 75
        url_display = url
        if len(url_display) > 60:
            url_display = url_display[:57] + "..."
        
        url_color = '#b0b0b0' if is_current else '#888888'
        draw.text((x + 15, url_y), url_display, fill=url_color, font=url_font)
    
    def _generate_empty_tabs_image(self) -> bytes:
        """Generate an image for when no tabs are open"""
        width = 800
        height = 400
        img = Image.new('RGB', (width, height), color='#1e1e1e')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        except:
            font = ImageFont.load_default()
        
        text = "No tabs open"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (width - text_width) // 2
        
        draw.text((text_x, height // 2 - 20), text, fill='#888888', font=font)
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()
    
    def _generate_error_image(self, error_msg: str) -> bytes:
        """Generate an error image"""
        width = 800
        height = 400
        img = Image.new('RGB', (width, height), color='#1e1e1e')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        except:
            font = ImageFont.load_default()
        
        text = f"Error generating tab view:\n{error_msg[:100]}"
        draw.text((50, height // 2 - 20), text, fill='#f44336', font=font)
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()

