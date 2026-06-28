import re
import unicodedata

PLACEHOLDER_PATTERN = re.compile(
    r"\[[^\]\n]{1,80}\]|\{[^{}\n]{1,80}\}|<[^<>\n]{1,80}>"
)
NAME_INTRO_PATTERN = re.compile(r"\bменя\s+зовут\b", re.IGNORECASE)
LATIN_TOKEN_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[.+#/-][A-Za-z0-9+#]+)*"
)
BASE_TECH_TERMS = {
    "ai",
    "ai-assisted",
    "api",
    "blockchain",
    "chatgpt",
    "css",
    "cursor",
    "docker",
    "git",
    "html",
    "javascript",
    "n8n",
    "playwright",
    "python",
    "rest",
    "telegram",
    "ubuntu",
    "vps",
    "web3",
}
COMMON_PUNCTUATION = set(".,:;!?…—–-()«»\"'/%+#№@&")


def _looks_technical(token: str) -> bool:
    return (
        any(char.isdigit() for char in token)
        or any(char in ".+#/-" for char in token)
        or token.isupper()
        or any(char.isupper() for char in token[1:])
    )


def build_allowed_tech_terms(candidate_profile: str, vacancy_text: str) -> set[str]:
    allowed = set(BASE_TECH_TERMS)
    for token in LATIN_TOKEN_PATTERN.findall(f"{candidate_profile}\n{vacancy_text}"):
        if _looks_technical(token):
            allowed.add(token.casefold())
    return allowed


def _is_cyrillic(char: str) -> bool:
    return 0x0400 <= ord(char) <= 0x052F


def _is_emoji_or_unusual_symbol(char: str) -> bool:
    if char in COMMON_PUNCTUATION:
        return False
    category = unicodedata.category(char)
    return category in {"So", "Sk"} or category.startswith(("S", "P"))


def cover_letter_issues(
    text: str,
    *,
    allowed_latin_terms: set[str],
) -> list[str]:
    issues: list[str] = []
    length = len(text)
    if not 500 <= length <= 800:
        issues.append(f"длина {length} знаков вне диапазона 500–800")
    if PLACEHOLDER_PATTERN.search(text):
        issues.append("обнаружена шаблонная заглушка в скобках")
    if NAME_INTRO_PATTERN.search(text):
        issues.append("обнаружено ненужное представление по имени")
    if any(
        char.isalpha()
        and not _is_cyrillic(char)
        and not ("A" <= char <= "Z" or "a" <= char <= "z")
        for char in text
    ):
        issues.append("обнаружен посторонний алфавит")
    if any(_is_emoji_or_unusual_symbol(char) for char in text):
        issues.append("обнаружены эмодзи или необычные символы")

    latin_tokens = LATIN_TOKEN_PATTERN.findall(text)
    unknown_latin = {
        token
        for token in latin_tokens
        if token.casefold() not in BASE_TECH_TERMS
        and token.casefold() not in allowed_latin_terms
    }
    if unknown_latin:
        issues.append("обнаружены неизвестные латинские слова")

    text_without_allowed = text
    for token in latin_tokens:
        if (
            token.casefold() in BASE_TECH_TERMS
            or token.casefold() in allowed_latin_terms
        ):
            text_without_allowed = text_without_allowed.replace(token, "")
    letters = [char for char in text_without_allowed if char.isalpha()]
    cyrillic = [char for char in letters if _is_cyrillic(char)]
    if letters and len(cyrillic) / len(letters) < 0.8:
        issues.append("доля русского текста ниже 80%")
    return issues
