"""
Tag validation and correction utilities for LLM output.

This module provides functions to validate and fix mismatched speaker tags
in the output from local LLMs.
"""

import re
from typing import List, Tuple, Optional, Dict
from difflib import SequenceMatcher
from src.chinese_novel.speaker_ids import normalize_speaker_id
from src.tag_validation import structural_tags, tag_errors


def validate_and_fix_tags(text: str) -> Tuple[str, List[Dict]]:
    """
    Validate and fix mismatched speaker tags in text.
    
    Args:
        text: Input text with speaker tags
        
    Returns:
        Tuple of (fixed_text, list of corrections made)
    """
    corrections, replacements, stack = [], [], []
    # Keep all offsets tied to the original source. Replacing a long control
    # closer with a short Chinese ID must not shift later repair positions.
    for match in structural_tags(text):
        name = match[2].lower()
        if not match[1]:
            stack.append((match[2], match.start()))
        elif stack:
            open_tag, open_pos = stack.pop()
            if open_tag.lower() != name:
                fix = f'[/{open_tag}]'
                corrections.append({'type': 'mismatch', 'expected': fix,
                                    'found': match[0], 'position': match.start(), 'fix': fix})
                replacements.append((match.start(), match.end(), fix))
    for start, end, fix in reversed(replacements):
        text = text[:start] + fix + text[end:]
    for open_tag, open_pos in reversed(stack):
        fix = f'[/{open_tag}]'
        corrections.append({'type': 'unclosed', 'tag': f'[{open_tag}]',
                            'position': open_pos, 'fix': fix})
        text += fix
    return text, corrections


def find_similar_speakers(speakers: List[str], threshold: float = 0.8) -> List[Tuple[str, str, float]]:
    """
    Find speakers that might be the same person with different name formats.
    
    Args:
        speakers: List of speaker names
        threshold: Similarity threshold (0-1), default 0.8
        
    Returns:
        List of tuples (speaker1, speaker2, similarity_score)
    """
    similar_pairs = []
    
    for i, sp1 in enumerate(speakers):
        for sp2 in speakers[i+1:]:
            score = SequenceMatcher(None, sp1.lower(), sp2.lower()).ratio()
            if score >= threshold:
                similar_pairs.append((sp1, sp2, round(score, 2)))
    
    return similar_pairs


def normalize_speaker_name(name: str) -> str:
    """
    Normalize speaker name for comparison.
    
    - Convert to lowercase
    - Replace spaces with hyphens
    - Remove special characters
    """
    return normalize_speaker_id(name)


def suggest_speaker_mapping(speakers: List[str], known_speakers: List[str]) -> Dict[str, str]:
    """
    Suggest mappings from detected speakers to known speakers.
    
    Args:
        speakers: List of speakers found in current chunk
        known_speakers: List of known speakers from previous chunks
        
    Returns:
        Dict mapping detected speaker -> suggested known speaker
    """
    mapping = {}
    
    for speaker in speakers:
        if speaker in known_speakers:
            continue  # Already known
        
        normalized = normalize_speaker_name(speaker)
        if not normalized:
            continue
        
        # Try exact match with normalized
        for known in known_speakers:
            known_normalized = normalize_speaker_name(known)
            if normalized == known_normalized:
                mapping[speaker] = known
                break
        
        # Try fuzzy match if no exact match
        if speaker not in mapping:
            best_match = None
            best_score = 0
            
            for known in known_speakers:
                known_normalized = normalize_speaker_name(known)
                score = SequenceMatcher(None, normalized, known_normalized).ratio()
                if score > best_score and score >= 0.7:
                    best_score = score
                    best_match = known
            
            if best_match:
                mapping[speaker] = best_match
    
    return mapping


def apply_speaker_mapping(text: str, speaker_map: Dict[str, str]) -> str:
    """
    Apply speaker name mapping to text.
    
    Args:
        text: Text with speaker tags
        speaker_map: Dict mapping old speaker names to new ones
        
    Returns:
        Text with updated speaker names
    """
    for old_name, new_name in speaker_map.items():
        # Replace opening tags
        text = re.sub(
            rf'\[{re.escape(old_name)}\]',
            f'[{new_name}]',
            text
        )
        # Replace closing tags
        text = re.sub(
            rf'\[/{re.escape(old_name)}\]',
            f'[/{new_name}]',
            text
        )
    
    return text


def validate_tags_strict(text: str) -> Tuple[bool, List[str]]:
    """
    Strictly validate that all tags are properly matched.
    
    Args:
        text: Text with speaker tags
        
    Returns:
        Tuple of (is_valid, list of errors)
    """
    errors = tag_errors(text)
    return len(errors) == 0, errors


if __name__ == "__main__":
    # Test the validation
    test_text = """
[narrator]Chapter One[/narrator]
[mrs-bennet-female]My dear Mr. Bennet[/mrs-bennet-female]
[mr-bennet-male]I have not[/mr-bennet-male]
[mrs-bennet-female]But it is; for Mrs. Long has just been here[/mr-bennet-male]
[narrator]This was invitation enough[/narrator]
"""
    
    fixed, corrections = validate_and_fix_tags(test_text)
    print("Original:")
    print(test_text)
    print("\nCorrected:")
    print(fixed)
    print("\nCorrections:")
    for c in corrections:
        print(f"  {c}")
