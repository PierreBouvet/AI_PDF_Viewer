import re
import io
import markdown
from backend.logger import logger

def render_markdown(text: str) -> str:
    """
    Preserves LaTeX math blocks ($$..$$, $..$, \\[..\\], \\(..\\), \\begin{equation}..\\end{equation})
    from being mangled by Markdown, protects fenced/inline code from math regexes,
    then converts Markdown to HTML, and restores safely escaped math blocks for KaTeX.
    """
    import uuid
    import html

    code_blocks = {}
    def repl_code(m):
        t = f"CODEBLOCK{uuid.uuid4().hex}CODEBLOCK"
        code_blocks[t] = m.group(0)
        return t

    # 1. Protect fenced code blocks and inline code from math regex
    text = re.sub(r'(```[\s\S]*?```|`[^`\n]+?`)', repl_code, text)

    math_blocks = {}

    def repl_display(match):
        token = f"MATHBLOCK{uuid.uuid4().hex}MATHBLOCK"
        math_blocks[token] = f"$${html.escape(match.group(1))}$$"
        return token

    def repl_inline(match):
        token = f"MATHBLOCK{uuid.uuid4().hex}MATHBLOCK"
        math_blocks[token] = f"${html.escape(match.group(1))}$"
        return token

    # 2. LaTeX environments: equation, align, gather, multline
    env_pattern = re.compile(
        r'\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}(.*?)\\end\{\1\}',
        re.DOTALL
    )
    def repl_env(match):
        token = f"MATHBLOCK{uuid.uuid4().hex}MATHBLOCK"
        env_name = match.group(1).rstrip('*')
        content = match.group(2)
        if env_name in ('align', 'gather', 'multline'):
            math_blocks[token] = f"$$\\begin{{aligned}}{html.escape(content)}\\end{{aligned}}$$"
        else:
            math_blocks[token] = f"$${html.escape(content)}$$"
        return token
    text = env_pattern.sub(repl_env, text)

    # 3. Bracket display math \[ ... \]
    bracket_display = re.compile(r'\\\[(.*?)\\\]', re.DOTALL)
    text = bracket_display.sub(repl_display, text)

    # 4. Double-dollar display math $$ ... $$
    display_pattern = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    text = display_pattern.sub(repl_display, text)

    # 5. Bracket inline math \( ... \)
    bracket_inline = re.compile(r'\\\((.*?)\\\)', re.DOTALL)
    text = bracket_inline.sub(repl_inline, text)

    # 6. Inline math $ ... $
    inline_pattern = re.compile(r'(?<!\$)\$([^$\n]+?)\$(?!\$)')
    text = inline_pattern.sub(repl_inline, text)

    # 7. Restore protected code blocks before markdown rendering
    for t, orig in code_blocks.items():
        text = text.replace(t, orig)

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

