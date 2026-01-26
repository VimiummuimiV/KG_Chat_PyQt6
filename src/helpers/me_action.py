"""Helper for /me action message formatting"""

def format_me_action(text: str, username: str) -> tuple[str, bool]:
    """Convert '/me action' to 'username action'.
    
    Args:
        text: Message text (may contain /me prefix)
        username: Username to prepend for /me actions
        
    Returns:
        Tuple of (formatted_text, is_system_message)
        - formatted_text: Original text or formatted as "username action"
        - is_system_message: True if this was a /me action
        
    Example:
        >>> format_me_action("/me waves", "Alice")
        ("Alice waves", True)
        >>> format_me_action("hello world", "Bob")
        ("hello world", False)
    """
    if text and text.strip().startswith('/me '):
        action = text.strip()[4:]  # Remove '/me ' prefix
        return f"{username} {action}", True
    return text, False