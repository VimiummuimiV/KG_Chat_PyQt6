"""Global HTML processor for safe display in Qt widgets"""
import re
from html import escape, unescape
from typing import Optional, Dict, List


class HTMLProcessor:
    """
    Universal HTML processor for converting various HTML to Qt-safe format
    Handles: links, formatting, blocks, images, hidden content, and more
    """
    
    # Tags allowed in Qt Rich Text
    ALLOWED_TAGS = {
        'p', 'br', 'b', 'i', 'u', 'strong', 'em', 'a', 'span', 'div',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'img',
        'blockquote', 'code', 'pre',
        'font', 'center'
    }
    
    # Tags that should be completely removed with their content
    DANGEROUS_TAGS = {
        'script', 'style', 'iframe', 'object', 'embed', 'applet',
        'meta', 'link', 'base', 'form', 'input', 'button', 'select', 'textarea'
    }
    
    # Attributes allowed on specific tags
    ALLOWED_ATTRIBUTES = {
        'a': {'href', 'title', 'target'},
        'img': {'src', 'alt', 'width', 'height', 'title'},
        'span': {'style'},
        'div': {'style', 'class'},
        'font': {'color', 'size', 'face'},
        'p': {'style'},
        'h1': {'style'}, 'h2': {'style'}, 'h3': {'style'},
        'h4': {'style'}, 'h5': {'style'}, 'h6': {'style'},
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize HTML processor
        
        Args:
            config: Optional configuration dict with processor settings
        """
        self.config = config or {}
        self.show_hidden_content = self.config.get('show_hidden_content', False)
        self.max_image_width = self.config.get('max_image_width', 600)
        self.max_image_height = self.config.get('max_image_height', 400)
        self.hidden_text_label = self.config.get('hidden_text_label', '[Hidden content - click to expand]')
    
    def process(self, html: str, context: str = 'general') -> str:
        """
        Main processing function - converts HTML to Qt-safe format
        
        Args:
            html: Raw HTML string
            context: Context hint ('bio', 'message', 'general', etc.)
        
        Returns:
            Processed HTML safe for Qt display
        """
        if not html or not isinstance(html, str):
            return ""
        
        # Step 1: Remove dangerous tags
        html = self._remove_dangerous_tags(html)
        
        # Step 2: Process hidden content blocks
        html = self._process_hidden_blocks(html)
        
        # Step 3: Preserve and clean links
        html, links = self._extract_links(html)
        
        # Step 4: Preserve and clean images
        html, images = self._extract_images(html)
        
        # Step 5: Process text formatting
        html = self._process_formatting(html)
        
        # Step 6: Filter allowed tags and attributes
        html = self._filter_tags_and_attributes(html)
        
        # Step 7: Restore links
        html = self._restore_links(html, links)
        
        # Step 8: Restore images
        html = self._restore_images(html, images)
        
        # Step 9: Clean up whitespace
        html = self._clean_whitespace(html)
        
        # Step 10: Wrap in container
        html = self._wrap_content(html, context)
        
        return html
    
    def _remove_dangerous_tags(self, html: str) -> str:
        """Remove dangerous tags and their content"""
        for tag in self.DANGEROUS_TAGS:
            # Remove opening to closing tag with content
            pattern = rf'<{tag}[^>]*>.*?</{tag}>'
            html = re.sub(pattern, '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove self-closing tags
            pattern = rf'<{tag}[^>]*/?>'
            html = re.sub(pattern, '', html, flags=re.IGNORECASE)
        return html
    
    def _process_hidden_blocks(self, html: str) -> str:
        """Process hidden content blocks (<!--hide--> patterns)"""
        if self.show_hidden_content:
            # Show hidden content, just remove the hide markers
            html = re.sub(r'<!--hide\d*-->', '', html)
            return html
        
        # Replace hidden blocks with placeholder
        def replace_hidden(match):
            return f'<i style="color: #888;">{self.hidden_text_label}</i>'
        
        # Match <!--hide--> ... <!--hide3--> pattern
        html = re.sub(
            r'<!--hide-->.*?<!--hide3-->',
            replace_hidden,
            html,
            flags=re.DOTALL
        )
        
        # Also handle other hide patterns
        html = re.sub(
            r'<!--hide\d*-->.*?<!--/hide\d*-->',
            replace_hidden,
            html,
            flags=re.DOTALL
        )
        
        return html
    
    def _extract_links(self, html: str) -> tuple:
        """Extract and sanitize links, return (html_with_placeholders, links_list)"""
        links = []
        
        def save_link(match):
            # Extract href and text
            full_tag = match.group(0)
            href_match = re.search(r'href=["\']([^"\']+)["\']', full_tag, re.IGNORECASE)
            text_match = re.search(r'>([^<]+)<', full_tag)
            
            if href_match:
                url = href_match.group(1)
                text = text_match.group(1) if text_match else url
                
                # Sanitize URL (basic XSS prevention)
                if url.strip().lower().startswith(('javascript:', 'data:', 'vbscript:')):
                    return escape(text)  # Don't create link for dangerous URLs
                
                links.append({
                    'url': escape(url),
                    'text': escape(text),
                    'target': '_blank'  # Always open in new window
                })
                return f'__LINK_{len(links) - 1}__'
            
            return match.group(0)
        
        html = re.sub(
            r'<a[^>]*>.*?</a>',
            save_link,
            html,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        return html, links
    
    def _extract_images(self, html: str) -> tuple:
        """Extract and sanitize images, return (html_with_placeholders, images_list)"""
        images = []
        
        def save_image(match):
            full_tag = match.group(0)
            src_match = re.search(r'src=["\']([^"\']+)["\']', full_tag, re.IGNORECASE)
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', full_tag, re.IGNORECASE)
            
            if src_match:
                src = src_match.group(1)
                alt = alt_match.group(1) if alt_match else ''
                
                # Only allow http/https images
                if src.strip().lower().startswith(('http://', 'https://')):
                    images.append({
                        'src': escape(src),
                        'alt': escape(alt),
                        'max_width': self.max_image_width,
                        'max_height': self.max_image_height
                    })
                    return f'__IMAGE_{len(images) - 1}__'
            
            return ''  # Remove invalid images
        
        html = re.sub(
            r'<img[^>]*>',
            save_image,
            html,
            flags=re.IGNORECASE
        )
        
        return html, images
    
    def _process_formatting(self, html: str) -> str:
        """Process text formatting tags"""
        # Convert <br /> to <br>
        html = html.replace('<br />', '<br>')
        html = html.replace('<br/>', '<br>')
        
        # Normalize line breaks
        html = re.sub(r'\r\n|\r', '\n', html)
        
        return html
    
    def _filter_tags_and_attributes(self, html: str) -> str:
        """Filter HTML to only allowed tags and attributes"""
        def filter_tag(match):
            full_tag = match.group(0)
            tag_name = match.group(1).lower().strip('/')
            is_closing = full_tag.startswith('</')
            is_self_closing = full_tag.endswith('/>')
            
            # Extract base tag name (without namespace)
            base_tag = tag_name.split(':')[-1]
            
            # Check if tag is allowed
            if base_tag not in self.ALLOWED_TAGS:
                return ''  # Remove disallowed tags
            
            # For closing tags, just return if allowed
            if is_closing:
                return f'</{base_tag}>'
            
            # For opening/self-closing tags, filter attributes
            allowed_attrs = self.ALLOWED_ATTRIBUTES.get(base_tag, set())
            
            if not allowed_attrs:
                # No attributes allowed for this tag
                return f'<{base_tag}>' if not is_self_closing else f'<{base_tag} />'
            
            # Extract and filter attributes
            attrs_match = re.search(r'<' + re.escape(tag_name) + r'\s+([^>]+)', full_tag, re.IGNORECASE)
            if not attrs_match:
                return f'<{base_tag}>' if not is_self_closing else f'<{base_tag} />'
            
            attrs_str = attrs_match.group(1)
            filtered_attrs = []
            
            # Parse attributes
            attr_pattern = r'(\w+)\s*=\s*["\']([^"\']*)["\']'
            for attr_match in re.finditer(attr_pattern, attrs_str):
                attr_name = attr_match.group(1).lower()
                attr_value = attr_match.group(2)
                
                if attr_name in allowed_attrs:
                    # Additional sanitization for style attributes
                    if attr_name == 'style':
                        attr_value = self._sanitize_style(attr_value)
                    filtered_attrs.append(f'{attr_name}="{attr_value}"')
            
            if filtered_attrs:
                attrs_joined = ' ' + ' '.join(filtered_attrs)
            else:
                attrs_joined = ''
            
            if is_self_closing:
                return f'<{base_tag}{attrs_joined} />'
            else:
                return f'<{base_tag}{attrs_joined}>'
        
        html = re.sub(r'<(/?\w+:?\w*)[^>]*>', filter_tag, html)
        return html
    
    def _sanitize_style(self, style: str) -> str:
        """Sanitize CSS style attribute"""
        # Remove potentially dangerous CSS
        dangerous_patterns = [
            r'javascript:',
            r'expression\s*\(',
            r'@import',
            r'behavior:',
            r'-moz-binding:',
        ]
        
        for pattern in dangerous_patterns:
            style = re.sub(pattern, '', style, flags=re.IGNORECASE)
        
        return style
    
    def _restore_links(self, html: str, links: List[Dict]) -> str:
        """Restore links from placeholders"""
        for idx, link in enumerate(links):
            placeholder = f'__LINK_{idx}__'
            link_html = f'<a href="{link["url"]}" target="{link["target"]}">{link["text"]}</a>'
            html = html.replace(placeholder, link_html)
        return html
    
    def _restore_images(self, html: str, images: List[Dict]) -> str:
        """Restore images from placeholders"""
        for idx, img in enumerate(images):
            placeholder = f'__IMAGE_{idx}__'
            img_html = f'<img src="{img["src"]}" alt="{img["alt"]}" style="max-width: {img["max_width"]}px; max-height: {img["max_height"]}px;" />'
            html = html.replace(placeholder, img_html)
        return html
    
    def _clean_whitespace(self, html: str) -> str:
        """Clean up excessive whitespace"""
        # Replace multiple newlines with double line breaks
        html = re.sub(r'\n\s*\n\s*\n+', '<br><br>', html)
        
        # Clean up spaces around tags
        html = re.sub(r'>\s+<', '><', html)
        
        return html
    
    def _wrap_content(self, html: str, context: str) -> str:
        """Wrap content in appropriate container"""
        # Add base paragraph wrapper for better formatting
        if not html.strip().startswith('<'):
            html = f'<p>{html}</p>'
        
        # Add container div with context-specific styling
        container_style = 'margin: 0; padding: 0; word-wrap: break-word;'
        
        return f'<div style="{container_style}">{html}</div>'
    
    def strip_all_html(self, html: str) -> str:
        """Strip all HTML tags and return plain text"""
        if not html:
            return ""
        
        # Remove all tags
        text = re.sub(r'<[^>]+>', '', html)
        
        # Decode HTML entities
        text = unescape(text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def extract_text_preview(self, html: str, max_length: int = 200) -> str:
        """Extract plain text preview from HTML"""
        text = self.strip_all_html(html)
        
        if len(text) <= max_length:
            return text
        
        # Cut at word boundary
        text = text[:max_length]
        last_space = text.rfind(' ')
        if last_space > max_length * 0.8:  # At least 80% filled
            text = text[:last_space]
        
        return text + '...'


# Global processor instance (can be reconfigured)
_global_processor = None


def get_processor(config: Optional[Dict] = None) -> HTMLProcessor:
    """Get or create global HTML processor instance"""
    global _global_processor
    if _global_processor is None or config is not None:
        _global_processor = HTMLProcessor(config)
    return _global_processor


# Convenience functions for common use cases
def process_html(html: str, context: str = 'general', config: Optional[Dict] = None) -> str:
    """Process HTML for safe display"""
    processor = get_processor(config)
    return processor.process(html, context)


def process_bio_html(html: str, config: Optional[Dict] = None) -> str:
    """Process biography HTML specifically"""
    return process_html(html, context='bio', config=config)


def process_message_html(html: str, config: Optional[Dict] = None) -> str:
    """Process message HTML specifically"""
    return process_html(html, context='message', config=config)


def strip_html(html: str) -> str:
    """Strip all HTML and return plain text"""
    processor = get_processor()
    return processor.strip_all_html(html)


def extract_preview(html: str, max_length: int = 200) -> str:
    """Extract text preview from HTML"""
    processor = get_processor()
    return processor.extract_text_preview(html, max_length)