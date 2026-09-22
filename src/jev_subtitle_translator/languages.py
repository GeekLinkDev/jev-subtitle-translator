"""Language codes accepted on the command line and their names used in prompts."""

# Mirrors GeekLink's LANGUAGE_OPTIONS / _get_language_name so both tools send
# the same language wording to the model.
LANGUAGE_NAMES: dict[str, str] = {
    "zh-cn": "Chinese",
    "zh-tw": "Traditional Chinese",
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "th": "Thai",
    "vi": "Vietnamese",
    "ro": "Romanian",
    "sl": "Slovenian",
    "hi": "Hindi",
    "tr": "Turkish",
    "nl": "Dutch",
    "pl": "Polish",
    "sv": "Swedish",
    "uk": "Ukrainian",
    "ca": "Catalan",
    "cs": "Czech",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "hu": "Hungarian",
    "el": "Greek",
    "ms": "Malay",
    "hr": "Croatian",
    "sk": "Slovak",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "he": "Hebrew",
    "fa": "Persian",
    "tl": "Filipino",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "az": "Azerbaijani",
    "bn": "Bengali",
    "ur": "Urdu",
    "ta": "Tamil",
    "ne": "Nepali",
    "sw": "Swahili",
    "ka": "Georgian",
    "is": "Icelandic",
}


def language_name(code_or_name: str) -> str:
    """Return the prompt wording for a language code; unknown values pass through."""

    return LANGUAGE_NAMES.get(code_or_name.strip().lower(), code_or_name.strip())
