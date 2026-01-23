"""
URL normalization utility for gym base URLs
"""


def normalize_base_url(url: str) -> str:
    """
    Normalize a base URL for duplicate checking.
    
    Normalization rules:
    - Strip whitespace from beginning and end
    - Convert to lowercase
    - Remove trailing slash
    
    Args:
        url: The base URL to normalize
        
    Returns:
        Normalized URL string
        
    Examples:
        >>> normalize_base_url("https://Example.com/")
        'https://example.com'
        >>> normalize_base_url("  https://example.com  ")
        'https://example.com'
        >>> normalize_base_url("HTTPS://EXAMPLE.COM")
        'https://example.com'
    """
    if not url:
        return url
    
    # Strip whitespace
    normalized = url.strip()
    
    # Convert to lowercase
    normalized = normalized.lower()
    
    # Remove trailing slash
    normalized = normalized.rstrip('/')
    
    return normalized

