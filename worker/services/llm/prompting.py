"""Prompt templates for the multi-agent graph nodes.

Centralizing prompts keeps node logic lean and makes each prompt unit-testable
without invoking an LLM. Each node formats its own prompt and passes it to the
LLM gateway (``LLMRouter``) for structured output.
"""

CLEANER_PROMPT = """You are a transcript cleaner. Normalize the following raw meeting
transcript: fix typos and formatting, split it into speaker segments, and remove
noise (e.g. "um", "uh", crosstalk artifacts). Respond ONLY with valid JSON matching:

{{
  "cleaned_text": "...",
  "segments": [{{"speaker": "...", "text": "...", "order": 0}}]
}}

Transcript:
{transcript}
"""

EXTRACTOR_PROMPT = """You are an action-item extractor. From the cleaned meeting transcript
below, extract concrete action items with assignee, task, optional deadline, priority
(low/medium/high/urgent), and a confidence score in [0,1]. Respond ONLY with JSON:

{{
  "action_items": [
    {{"assignee": "...", "task": "...", "deadline": null, "priority": "medium", "confidence": 0.9}}
  ]
}}

Cleaned transcript:
{cleaned_text}
"""

AUDITOR_PROMPT = """You are a decision auditor. From the cleaned meeting transcript below,
identify explicit decisions that were made, including any dissent points. For each
decision provide context, impact, whether there was explicit dissent (has_dissent),
and a confidence score in [0,1]. Respond ONLY with JSON:

{{
  "decisions": [
    {{"decision": "...", "impact": null, "context": null, "has_dissent": false, "confidence": 0.9}}
  ]
}}

Cleaned transcript:
{cleaned_text}
"""

INSPECTOR_PROMPT = """You are a quality inspector. Given the source transcript and a set of
extracted action items and decisions, verify that each extracted item is actually
supported by the source text. Identify hallucinations, omissions, or low-confidence
extractions. Respond ONLY with JSON:

{{
  "findings": [
    {{"item_index": 0, "item_type": "action", "issue": "...", "severity": "warning"}}
  ],
  "overall_confidence": 0.9
}}

Source transcript:
{source_text}

Extracted action items:
{action_items}

Extracted decisions:
{decisions}
"""


def cleaner_prompt(transcript: str) -> str:
    return CLEANER_PROMPT.format(transcript=transcript)


def extractor_prompt(cleaned_text: str) -> str:
    return EXTRACTOR_PROMPT.format(cleaned_text=cleaned_text)


def auditor_prompt(cleaned_text: str) -> str:
    return AUDITOR_PROMPT.format(cleaned_text=cleaned_text)


def inspector_prompt(source_text: str, action_items: list, decisions: list) -> str:
    return INSPECTOR_PROMPT.format(
        source_text=source_text,
        action_items=str(action_items),
        decisions=str(decisions),
    )
