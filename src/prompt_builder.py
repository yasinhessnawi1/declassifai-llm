"""Prompt builder for chat fine-tuning format.

Converts raw dataset entries into chat messages (system/user/assistant)
that match the format the model will see at inference time.
"""

import json
from typing import Dict, List, Any

from .config_loader import Config


def build_entity_type_list(entity_types: Dict[str, str]) -> str:
    """Build a formatted entity type list for the user prompt.

    Args:
        entity_types: Mapping of entity type names to descriptions.

    Returns:
        Formatted string like:
        - PERSON: Full names of individuals
        - EMAIL_ADDRESS: Email addresses
    """
    lines = []
    for name, description in entity_types.items():
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def format_output(entities: Dict[str, List[str]]) -> str:
    """Format entity output as compact JSON string.

    Args:
        entities: Dict mapping entity type to list of extracted strings.

    Returns:
        JSON string of the output.
    """
    return json.dumps(entities, ensure_ascii=False, separators=(",", ":"))


def build_chat_messages(
    text: str,
    entities: Dict[str, List[str]],
    cfg: Config,
) -> List[Dict[str, str]]:
    """Build a complete chat message sequence for one training sample.

    Args:
        text: The Norwegian input text.
        entities: Ground truth entity dict from the dataset.
        cfg: Config object with prompt templates and entity types.

    Returns:
        List of message dicts: [system, user, assistant].
    """
    entity_type_list = build_entity_type_list(cfg.entity_types)

    user_content = cfg.prompt.user_template.format(
        entity_types=entity_type_list,
        text=text,
    )

    # Filter output to only include entity types from config
    filtered_output = {}
    for etype in cfg.entity_types:
        filtered_output[etype] = entities.get(etype, [])

    assistant_content = format_output(filtered_output)

    messages = [
        {"role": "system", "content": cfg.prompt.system_instruction.strip()},
        {"role": "user", "content": user_content.strip()},
        {"role": "assistant", "content": assistant_content},
    ]

    return messages


def build_inference_messages(
    text: str,
    cfg: Config,
) -> List[Dict[str, str]]:
    """Build chat messages for inference (no assistant response).

    Args:
        text: The Norwegian input text.
        cfg: Config object.

    Returns:
        List of message dicts: [system, user] (no assistant).
    """
    entity_type_list = build_entity_type_list(cfg.entity_types)

    user_content = cfg.prompt.user_template.format(
        entity_types=entity_type_list,
        text=text,
    )

    return [
        {"role": "system", "content": cfg.prompt.system_instruction.strip()},
        {"role": "user", "content": user_content.strip()},
    ]
