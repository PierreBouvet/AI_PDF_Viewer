import re
import io
import markdown
from backend.logger import logger

def render_markdown(text: str) -> str:
    """
    Preserves LaTeX math blocks ($$..$$ and $..$) from being mangled by Markdown,
    then converts Markdown to HTML, and restores the safely escaped math blocks for KaTeX.
    """
    import uuid
    import html
    
    math_blocks = {}
    
    def repl_display(match):
        token = f"MATHBLOCK{uuid.uuid4().hex}MATHBLOCK"
        math_blocks[token] = f"$${html.escape(match.group(1))}$$"
        return token
        
    display_pattern = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    text = display_pattern.sub(repl_display, text)
    
    def repl_inline(match):
        token = f"MATHBLOCK{uuid.uuid4().hex}MATHBLOCK"
        math_blocks[token] = f"${html.escape(match.group(1))}$"
        return token
        
    inline_pattern = re.compile(r'(?<!\$)\$([^$]+?)\$(?!\$)')
    text = inline_pattern.sub(repl_inline, text)
    
    # LLMs frequently use 2-space indentation for nested lists, but Python-Markdown
    # strictly requires 4 spaces. This regex doubles leading spaces for list items.
    def double_spaces(m):
        return (m.group(1) * 2) + m.group(2)
    text = re.sub(r'^( +)([*+-] |\d+\. )', double_spaces, text, flags=re.MULTILINE)
    
    # Convert Markdown to HTML
    html_output = markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'])
    
    # Restore math blocks
    for token, original_math in math_blocks.items():
        html_output = html_output.replace(token, original_math)
        
    return html_output

def escape_html(text: str) -> str:
    """Basic HTML escaping."""
    import html
    return html.escape(text)
