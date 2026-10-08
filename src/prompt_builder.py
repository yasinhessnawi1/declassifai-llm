"""Prompt builder for chat fine-tuning format.

Converts raw dataset entries into chat messages (system/user/assistant)
that match the format the model will see at inference time.
"""

import json
from typing import Dict, List, Any, Optional, Sequence

from .config_loader import Config


def scope_types(cfg: Config, types: Optional[Sequence[str]] = None) -> List[str]:
    """Return the types an example is prompted for, in config order.

    An example annotated for only some types (a corpus record trusted for eight) must
    be prompted for exactly those: listing a type it was never annotated for, then
    showing no spans for it, teaches the model that the type does not occur.

    Args:
        cfg: Config whose `entity_types` fixes the order and the descriptions.
        types: The example's annotation scope, or None for every configured type.

    Returns:
        Type names in config order.
    """
    if types is None:
        return list(cfg.entity_types)
    unknown = set(types) - set(cfg.entity_types)
    if unknown:
        raise ValueError(f"example scope has types the config does not define: {sorted(unknown)}")
    wanted = set(types)
    return [t for t in cfg.entity_types if t in wanted]


def build_entity_type_list(entity_types: Dict[str, str], describe: bool = True) -> str:
    """Build a formatted entity type list for the user prompt.

    Args:
        entity_types: Mapping of entity type names to descriptions.

    Returns:
        Formatted string like:
        - PERSON: Full names of individuals
        - EMAIL_ADDRESS: Email addresses
    """
    if not describe:
        return ", ".join(entity_types)
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
    types: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """Build a complete chat message sequence for one training sample.

    Args:
        text: The Norwegian input text.
        entities: Ground truth entity dict from the dataset.
        cfg: Config object with prompt templates and entity types.
        types: The example's annotation scope; None means every configured type.

    Returns:
        List of message dicts: [system, user, assistant].
    """
    scope = scope_types(cfg, types)
    entity_type_list = build_entity_type_list(
        {t: cfg.entity_types[t] for t in scope}, cfg.prompt.describe_types)

    user_content = cfg.prompt.user_template.format(
        entity_types=entity_type_list,
        text=text,
    )

    # Only in-scope types appear in the target; out-of-scope spans are dropped.
    filtered_output = {}
    for etype in scope:
        spans = entities.get(etype, [])
        if spans or cfg.prompt.emit_empty:
            filtered_output[etype] = spans

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
    types: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """Build chat messages for inference (no assistant response).

    Args:
        text: The Norwegian input text.
        cfg: Config object.
        types: Types to ask for; None means every configured type.

    Returns:
        List of message dicts: [system, user] (no assistant).
    """
    scope = scope_types(cfg, types)
    entity_type_list = build_entity_type_list(
        {t: cfg.entity_types[t] for t in scope}, cfg.prompt.describe_types)

    user_content = cfg.prompt.user_template.format(
        entity_types=entity_type_list,
        text=text,
    )

    return [
        {"role": "system", "content": cfg.prompt.system_instruction.strip()},
        {"role": "user", "content": user_content.strip()},
    ]
