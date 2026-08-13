"""numberwords -- bidirectional text <-> number conversion.

Converts between numbers and their words in Mizo (Lushai):

    >>> import numberwords
    >>> numberwords.number_to_text(58)
    'sawm nga pariat'
    >>> numberwords.text_to_number("sawm nga pariat")
    58

The language behaviour is not written in this package. It is compiled from
languages/mizo.yaml -- one declarative spec per language -- into _mizo.py,
and interpreted by _render.py. See docs/architecture.md.

Mizo 0-100 is what this version supports; anything outside that range
raises NumberWordsError. There is no language parameter yet: adding one
before a second language exists would be guessing at its shape.

See https://github.com/instaword/numberwords
"""

# Imported as a module, not as bare names: `from ._render import
# render_number` would put `render_number` in the package namespace, where
# it reads as public API. Only what __all__ names is public.
from . import _render
from ._render import NumberWordsError

__all__ = ["number_to_text", "text_to_number", "NumberWordsError"]

__version__ = "0.1.0"


def number_to_text(n: int) -> str:
    """Return the Mizo words for `n`.

    Raises NumberWordsError if `n` is outside the supported range or is
    not an int. bool is not an int for this purpose.
    """
    return _render.render_number(n)


def text_to_number(text: str) -> int:
    """Return the number the Mizo `text` names.

    Accepts more spellings than number_to_text() produces -- case and
    diacritics are ignored, "-" works as a word separator, the connector
    "leh" is dropped, and a lone digit may be given in either of its forms
    ("khat" as well as "pakhat"). Raises NumberWordsError if the text names
    no number in the supported range, or is not a str.
    """
    return _render.parse_text(text)
