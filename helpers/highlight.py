"""
XSS-Safe Keyword Highlighting Utility.
Owner: Workstream A / Member 2 (Catalog, Brand & Search Specialist)
"""
import re
from markupsafe import Markup, escape


def highlight_query(value: any, query: str = None) -> Markup:
    """
    Highlights occurrences of `query` within `value` using <mark class="search-highlight">.
    Security: Strictly sanitizes and escapes all raw text before applying markup
    to prevent Cross-Site Scripting (XSS) attacks.
    """
    if value is None:
        return Markup("")

    str_value = str(value)
    if not query or not str(query).strip():
        return escape(str_value)

    # 1. Neutralize and HTML-escape raw text
    escaped_value = str(escape(str_value))
    clean_query = str(query).strip()

    # 2. Escape HTML entities for the query as well so matching works on escaped text
    escaped_query = str(escape(clean_query))
    if not escaped_query:
        return Markup(escaped_value)

    # 3. Case-insensitive regex match with capturing parentheses
    pattern = re.compile(f"({re.escape(escaped_query)})", re.IGNORECASE)

    # 4. Wrap matches in <mark class="search-highlight">
    highlighted = pattern.sub(r'<mark class="search-highlight">\1</mark>', escaped_value)

    return Markup(highlighted)

