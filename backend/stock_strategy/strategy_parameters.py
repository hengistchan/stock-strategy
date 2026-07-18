from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping


PARAMETER_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
PARAMETER_TYPES = frozenset({"int", "float", "bool", "string"})
MAX_PARAMETERS = 16
MAX_STRING_LENGTH = 200


class StrategyParameterError(ValueError):
    pass


def extract_parameter_definitions(source: str) -> list[dict[str, Any]]:
    """Parse the declarative STRATEGY_PARAMETERS mapping without executing code."""
    try:
        module = ast.parse(source, filename="strategy.py")
    except SyntaxError as error:
        raise StrategyParameterError(f"could not parse strategy parameters: {error.msg}") from error

    value_node: ast.expr | None = None
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "STRATEGY_PARAMETERS"
            for target in node.targets
        ):
            value_node = node.value
            break
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "STRATEGY_PARAMETERS"
        ):
            value_node = node.value
            break

    if value_node is None:
        return []
    try:
        raw = ast.literal_eval(value_node)
    except (ValueError, TypeError, SyntaxError) as error:
        raise StrategyParameterError(
            "STRATEGY_PARAMETERS must be a literal dictionary"
        ) from error
    if not isinstance(raw, dict):
        raise StrategyParameterError("STRATEGY_PARAMETERS must be a dictionary")
    if len(raw) > MAX_PARAMETERS:
        raise StrategyParameterError(
            f"STRATEGY_PARAMETERS supports at most {MAX_PARAMETERS} entries"
        )

    definitions: list[dict[str, Any]] = []
    for name, specification in raw.items():
        if not isinstance(name, str) or not PARAMETER_NAME_PATTERN.fullmatch(name):
            raise StrategyParameterError(f"invalid strategy parameter name: {name!r}")
        if not isinstance(specification, dict):
            raise StrategyParameterError(f"parameter {name!r} must use a dictionary spec")
        definitions.append(_normalize_definition(name, specification))
    return definitions


def load_parameter_definitions(path: str | Path) -> list[dict[str, Any]]:
    return extract_parameter_definitions(Path(path).read_text(encoding="utf-8"))


def resolve_parameter_values(
    definitions: list[dict[str, Any]],
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    supplied = dict(overrides or {})
    known = {definition["name"] for definition in definitions}
    unknown = sorted(set(supplied) - known)
    if unknown:
        raise StrategyParameterError(
            "unknown strategy parameters: " + ", ".join(unknown)
        )
    values: dict[str, Any] = {}
    for definition in definitions:
        name = definition["name"]
        value = supplied[name] if name in supplied else definition["default"]
        values[name] = validate_parameter_value(definition, value)
    return values


def validate_parameter_value(definition: Mapping[str, Any], value: Any) -> Any:
    name = str(definition["name"])
    parameter_type = str(definition["type"])
    normalized = _coerce_value(name, parameter_type, value)
    minimum = definition.get("min")
    maximum = definition.get("max")
    if minimum is not None and normalized < minimum:
        raise StrategyParameterError(f"parameter {name!r} must be >= {minimum}")
    if maximum is not None and normalized > maximum:
        raise StrategyParameterError(f"parameter {name!r} must be <= {maximum}")
    choices = definition.get("choices")
    if choices is not None and normalized not in choices:
        raise StrategyParameterError(
            f"parameter {name!r} must be one of {json.dumps(choices, ensure_ascii=False)}"
        )
    return normalized


def parse_parameter_assignment(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise StrategyParameterError("parameter must use NAME=JSON_VALUE")
    name, raw = value.split("=", 1)
    name = name.strip()
    if not PARAMETER_NAME_PATTERN.fullmatch(name):
        raise StrategyParameterError(f"invalid strategy parameter name: {name!r}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if not _is_scalar(parsed):
        raise StrategyParameterError(f"parameter {name!r} must be a scalar value")
    return name, parsed


def _normalize_definition(name: str, specification: Mapping[str, Any]) -> dict[str, Any]:
    parameter_type = str(specification.get("type", "")).lower()
    if parameter_type not in PARAMETER_TYPES:
        raise StrategyParameterError(
            f"parameter {name!r} type must be one of: {', '.join(sorted(PARAMETER_TYPES))}"
        )
    if "default" not in specification:
        raise StrategyParameterError(f"parameter {name!r} requires a default value")

    definition: dict[str, Any] = {
        "name": name,
        "label": str(specification.get("label") or name.replace("_", " "))[:80],
        "description": str(specification.get("description") or "")[:240],
        "type": parameter_type,
    }
    for boundary in ("min", "max", "step"):
        if boundary in specification:
            value = specification[boundary]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StrategyParameterError(
                    f"parameter {name!r} {boundary} must be numeric"
                )
            if not math.isfinite(float(value)):
                raise StrategyParameterError(
                    f"parameter {name!r} {boundary} must be finite"
                )
            definition[boundary] = value

    choices = specification.get("choices")
    if choices is not None:
        if not isinstance(choices, (list, tuple)) or not choices:
            raise StrategyParameterError(f"parameter {name!r} choices must be non-empty")
        definition["choices"] = [
            _coerce_value(name, parameter_type, choice) for choice in choices
        ]

    default = _coerce_value(name, parameter_type, specification["default"])
    definition["default"] = default
    validate_parameter_value(definition, default)

    candidates = specification.get("candidates", [default])
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise StrategyParameterError(f"parameter {name!r} candidates must be non-empty")
    normalized_candidates: list[Any] = []
    for candidate in candidates:
        normalized = validate_parameter_value(definition, candidate)
        if normalized not in normalized_candidates:
            normalized_candidates.append(normalized)
    definition["candidates"] = normalized_candidates
    return definition


def _coerce_value(name: str, parameter_type: str, value: Any) -> Any:
    if not _is_scalar(value):
        raise StrategyParameterError(f"parameter {name!r} must be a scalar value")
    if parameter_type == "bool":
        if not isinstance(value, bool):
            raise StrategyParameterError(f"parameter {name!r} must be boolean")
        return value
    if parameter_type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyParameterError(f"parameter {name!r} must be an integer")
        if not math.isfinite(float(value)) or int(value) != value:
            raise StrategyParameterError(f"parameter {name!r} must be an integer")
        return int(value)
    if parameter_type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyParameterError(f"parameter {name!r} must be numeric")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise StrategyParameterError(f"parameter {name!r} must be finite")
        return normalized
    if not isinstance(value, str):
        raise StrategyParameterError(f"parameter {name!r} must be a string")
    if len(value) > MAX_STRING_LENGTH:
        raise StrategyParameterError(
            f"parameter {name!r} cannot exceed {MAX_STRING_LENGTH} characters"
        )
    return value


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))
