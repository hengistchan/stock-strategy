from __future__ import annotations

import ast
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any
import uuid

from .strategy_parameters import StrategyParameterError, extract_parameter_definitions


MAX_STRATEGY_BYTES = 256 * 1024
STRATEGY_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
DEFAULT_STRATEGY_SOURCE = '''from stock_strategy.futu import *


STRATEGY_PARAMETERS = {}


class Strategy(StrategyBase):
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.symbol = declare_trig_symbol()

    def handle_data(self):
        # 在当前 K 线收盘产生信号，订单最早于下一根 K 线成交。
        pass
'''


class StrategyRepositoryError(Exception):
    """Base error for the local strategy repository."""


class StrategyNotFoundError(StrategyRepositoryError):
    pass


class StrategyConflictError(StrategyRepositoryError):
    pass


class StrategyValidationError(StrategyRepositoryError):
    pass


class StrategyPermissionError(StrategyRepositoryError):
    pass


class StrategyRepository:
    """Read examples and atomically manage user strategies inside the project."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.examples_root = (self.project_root / "examples").resolve()
        self.strategies_root = (self.project_root / "strategies").resolve()
        self.strategies_root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        strategies: list[dict[str, Any]] = []
        for root, group, readonly in (
            (self.examples_root, "示例策略", True),
            (self.strategies_root, "我的策略", False),
        ):
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.py")):
                strategies.append(self._metadata(path, group, readonly))
        return strategies

    def read(self, value: str) -> dict[str, Any]:
        path, group, readonly = self._resolve_readable(value)
        content = self._read_source(path)
        return {
            **self._metadata(path, group, readonly, content),
            "content": content,
        }

    def create(
        self,
        name: str,
        *,
        content: str | None = None,
        template_path: str | None = None,
    ) -> dict[str, Any]:
        stem = name[:-3] if name.endswith(".py") else name
        if not STRATEGY_NAME_PATTERN.fullmatch(stem):
            raise StrategyValidationError(
                "策略名必须以英文字母开头，且只能包含字母、数字和下划线。"
            )
        path = (self.strategies_root / f"{stem}.py").resolve()
        if path.parent != self.strategies_root:
            raise StrategyPermissionError("策略文件必须保存在 strategies/。")
        if path.exists():
            raise StrategyConflictError("同名策略已经存在。")

        source = content
        if source is None and template_path:
            source = self.read(template_path)["content"]
        if source is None:
            source = DEFAULT_STRATEGY_SOURCE
        validate_strategy_source(source)
        self._atomic_write(path, source)
        return self.read(str(path.relative_to(self.project_root)))

    def save(
        self, value: str, content: str, *, expected_revision: str | None
    ) -> dict[str, Any]:
        path = self._resolve_writable(value)
        current = self._read_source(path)
        current_revision = _revision(current)
        if expected_revision and expected_revision != current_revision:
            raise StrategyConflictError(
                "策略已被其他操作修改，请重新载入后再保存。"
            )
        validate_strategy_source(content)
        self._atomic_write(path, content)
        return self.read(str(path.relative_to(self.project_root)))

    def resolve_for_backtest(self, value: str) -> Path:
        path, _, _ = self._resolve_readable(value)
        return path

    def _resolve_readable(self, value: str) -> tuple[Path, str, bool]:
        candidate = (self.project_root / value).resolve()
        if candidate.suffix != ".py" or not candidate.is_file():
            raise StrategyNotFoundError("策略文件不存在或不是 Python 文件。")
        if candidate.parent == self.examples_root:
            return candidate, "示例策略", True
        if candidate.parent == self.strategies_root:
            return candidate, "我的策略", False
        raise StrategyPermissionError("策略文件必须位于 examples/ 或 strategies/。")

    def _resolve_writable(self, value: str) -> Path:
        try:
            path, _, readonly = self._resolve_readable(value)
        except StrategyNotFoundError:
            raise
        if readonly or path.parent != self.strategies_root:
            raise StrategyPermissionError("示例策略只读；请先复制到 strategies/。")
        return path

    def _read_source(self, path: Path) -> str:
        if path.stat().st_size > MAX_STRATEGY_BYTES:
            raise StrategyValidationError("策略文件不能超过 256 KiB。")
        return path.read_text(encoding="utf-8")

    def _metadata(
        self,
        path: Path,
        group: str,
        readonly: bool,
        content: str | None = None,
    ) -> dict[str, Any]:
        stat = path.stat()
        source = content if content is not None else self._read_source(path)
        return {
            "path": str(path.relative_to(self.project_root)),
            "name": path.stem.replace("_", " "),
            "group": group,
            "readonly": readonly,
            "revision": _revision(source),
            "size": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(
                timespec="seconds"
            ),
            "parameters": extract_parameter_definitions(source),
        }

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def validate_strategy_source(content: str) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_STRATEGY_BYTES:
        raise StrategyValidationError("策略文件不能超过 256 KiB。")
    try:
        module = ast.parse(content, filename="strategy.py")
    except SyntaxError as error:
        location = f"第 {error.lineno} 行" if error.lineno else "未知位置"
        raise StrategyValidationError(
            f"Python 语法错误（{location}）：{error.msg}"
        ) from error
    if not any(
        isinstance(node, ast.ClassDef) and node.name == "Strategy"
        for node in module.body
    ):
        raise StrategyValidationError("策略必须定义名为 Strategy 的类。")
    try:
        extract_parameter_definitions(content)
    except StrategyParameterError as error:
        raise StrategyValidationError(f"策略参数声明无效：{error}") from error


def _revision(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
