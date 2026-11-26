"""Versioned text-only input contract shared by new LoRA training and inference."""
LEGACY_POLICY = 'response_text_strip_v1'
BLANK_POLICY = 'response_text_blank_marker_v1'
EMPTY_MARKER = '[EMPTY_RESPONSE]'


def prepare_response(text, policy=LEGACY_POLICY):
    if text is not None and not isinstance(text, str):
        raise ValueError('LoRA response must be a string or null')
    text = (text or '').strip()
    if policy == LEGACY_POLICY:
        return text
    if policy == BLANK_POLICY:
        # Escape literal marker and leading escape character to avoid collisions.
        if not text:
            return EMPTY_MARKER
        return '\\' + text if text == EMPTY_MARKER or text.startswith('\\') else text
    raise ValueError('Unsupported LoRA input policy')
