"""Strip contact details before anything is stored. We keep links, not people."""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")
_HANDLE = re.compile(r"(?<![\w/])(?:u/|@)[A-Za-z0-9_-]{3,}")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email removed]", text or "")
    text = _PHONE.sub("[phone removed]", text)
    text = _HANDLE.sub("[handle removed]", text)
    return re.sub(r"\s+", " ", text).strip()
