"""Speaker Role Resolver: Maps generic labels (Speaker 0, Speaker 1) to legal identities."""

from typing import List, Dict
from worker.audit.services.diarization import Utterance


def resolve_speaker_roles(utterances: List[Utterance]) -> Dict[str, str]:
    """
    Analyzes conversation dialogue to map speaker labels to formal roles.
    Example:
      Speaker 0 -> Advisor / Institution
      Speaker 1 -> Client / Counterparty
    """
    role_map = {}
    
    # Analyze first few turns
    for u in utterances[:5]:
        text_lower = u.text.lower()
        if any(w in text_lower for w in ["advisor", "firm", "welcome", "consultation", "reviewing", "we provide", "fee is"]):
            role_map[u.speaker] = f"{u.speaker} (Advisor / Firm)"
        elif any(w in text_lower for w in ["thank you", "my portfolio", "i want", "i agree", "my risk"]):
            role_map[u.speaker] = f"{u.speaker} (Client / Account Holder)"

    # Default mappings if specific cues are absent
    for u in utterances:
        if u.speaker not in role_map:
            if u.speaker == "Speaker 0":
                role_map[u.speaker] = "Advisor / Lead"
            else:
                role_map[u.speaker] = "Client / Participant"

    return role_map

