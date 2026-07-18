from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .context import get_context
from .errors import DataUnavailableError
from .models import BarType, Contract, THType
from .timeframes import can_derive


class Series:
    def __init__(self, values: Iterable[float | bool]) -> None:
        self.values = [float(value) for value in values]

    def sma(self, period: int) -> Series:
        return MA(self, period)

    def ema(self, period: int) -> Series:
        return EMA(self, period)

    def __len__(self) -> int:
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, index: int) -> float:
        return self.values[index]

    def _binary(self, other: Any, operation: Callable[[float, float], float]) -> Series:
        right = _broadcast(other, len(self))
        return Series(operation(left, value) for left, value in zip(self.values, right))

    def _compare(self, other: Any, operation: Callable[[float, float], bool]) -> Series:
        return self._binary(other, lambda left, right: 1.0 if operation(left, right) else 0.0)

    def __add__(self, other: Any) -> Series:
        return self._binary(other, lambda left, right: left + right)

    __radd__ = __add__

    def __sub__(self, other: Any) -> Series:
        return self._binary(other, lambda left, right: left - right)

    def __rsub__(self, other: Any) -> Series:
        return Series(_broadcast(other, len(self))).__sub__(self)

    def __mul__(self, other: Any) -> Series:
        return self._binary(other, lambda left, right: left * right)

    __rmul__ = __mul__

    def __truediv__(self, other: Any) -> Series:
        return self._binary(other, lambda left, right: left / right if right else math.nan)

    def __rtruediv__(self, other: Any) -> Series:
        return Series(_broadcast(other, len(self))).__truediv__(self)

    def __pow__(self, other: Any) -> Series:
        return self._binary(other, math.pow)

    def __neg__(self) -> Series:
        return Series(-value for value in self.values)

    def __gt__(self, other: Any) -> Series:
        return self._compare(other, lambda left, right: left > right)

    def __ge__(self, other: Any) -> Series:
        return self._compare(other, lambda left, right: left >= right)

    def __lt__(self, other: Any) -> Series:
        return self._compare(other, lambda left, right: left < right)

    def __le__(self, other: Any) -> Series:
        return self._compare(other, lambda left, right: left <= right)


def register_indicator(indicator_name: str, script: str, param_list: list[str]) -> None:
    if not indicator_name or not isinstance(script, str):
        raise ValueError("register_indicator requires indicator_name and script")
    get_context().registered_indicators[indicator_name.upper()] = {
        "kind": "mylang",
        "script": script,
        "param_list": [name.upper() for name in param_list],
    }


def register_indicator_Python(indicator_name: str, script: str) -> None:
    if not indicator_name or not isinstance(script, str):
        raise ValueError("register_indicator_Python requires indicator_name and script")
    get_context().registered_indicators[indicator_name.upper()] = {
        "kind": "python",
        "script": script,
    }


def get_MyLang_indicator(
    indicator_name: str,
    variable_name: str,
    symbol: Contract,
    params: dict[str, Any],
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    registration = _registration(indicator_name, "mylang")
    environment = _series_environment(symbol, bar_type, select, session_type)
    environment.update({str(name).upper(): value for name, value in params.items()})
    outputs: dict[str, Any] = {}
    for statement in _statements(registration["script"]):
        match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::=|:|=)\s*(.+)$", statement
        )
        if not match:
            continue
        name, expression = match.groups()
        translated = _translate_expression(expression)
        scope = {**_MYLANG_FUNCTIONS, **environment, **outputs}
        try:
            outputs[name.upper()] = eval(translated, {"__builtins__": {}}, scope)
        except Exception as error:
            raise DataUnavailableError(
                f"MyLang indicator {indicator_name}.{name} could not be evaluated: {error}"
            ) from error
    try:
        return _last(outputs[variable_name.upper()])
    except KeyError as error:
        raise DataUnavailableError(
            f"MyLang indicator {indicator_name} has no output {variable_name}"
        ) from error


def get_Python_indicator(
    indicator_name: str,
    variable_name: str,
    symbol: Contract,
    params: dict[str, Any],
    bar_type: BarType = BarType.K_60M,
    select: int = 2,
    session_type: THType = THType.ALL,
) -> float:
    registration = _registration(indicator_name, "python")
    series = _series_environment(symbol, bar_type, select, session_type)
    outputs: dict[str, Any] = {}

    def input_parameter(name: str, default: Any = None) -> Any:
        return params.get(name, params.get(name.upper(), default))

    def output_parameter(**values: Any) -> None:
        outputs.update({name.upper(): value for name, value in values.items()})

    class Color:
        @staticmethod
        def hex(value: str) -> str:
            return value

    namespace = {
        "__builtins__": {
            "abs": abs,
            "bool": bool,
            "float": float,
            "int": int,
            "len": len,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
        },
        "__name__": "__main__",
        "indicator": lambda *_args, **_kwargs: None,
        "input_parameter": input_parameter,
        "output_parameter": output_parameter,
        "plot": lambda *_args, **_kwargs: None,
        "Color": Color,
        "close": lambda: series["CLOSE"],
        "open": lambda: series["OPEN"],
        "high": lambda: series["HIGH"],
        "low": lambda: series["LOW"],
        "volume": lambda: series["VOLUME"],
        "math": math,
    }
    try:
        exec(compile(registration["script"], f"<{indicator_name}>", "exec"), namespace)
    except Exception as error:
        raise DataUnavailableError(
            f"Python indicator {indicator_name} could not be evaluated: {error}"
        ) from error
    expected = variable_name.upper()
    if expected in outputs:
        return _last(outputs[expected])
    for name, value in outputs.items():
        if name.format(**params).upper() == expected:
            return _last(value)
    raise DataUnavailableError(
        f"Python indicator {indicator_name} has no output {variable_name}"
    )


def MA(value: Any, period: int) -> Series:
    series = _as_series(value)
    period = int(period)
    return Series(
        math.nan if index + 1 < period else statistics.fmean(series.values[index - period + 1 : index + 1])
        for index in range(len(series))
    )


def EMA(value: Any, period: int) -> Series:
    series = _as_series(value)
    period = int(period)
    output = [math.nan] * len(series)
    if len(series) < period:
        return Series(output)
    output[period - 1] = statistics.fmean(series.values[:period])
    alpha = 2 / (period + 1)
    for index in range(period, len(series)):
        output[index] = alpha * series[index] + (1 - alpha) * output[index - 1]
    return Series(output)


EXPMEMA = EMA


def SMA(value: Any, period: int, weight: int = 1) -> Series:
    series = _as_series(value)
    period, weight = int(period), int(weight)
    output: list[float] = []
    previous = series[0] if len(series) else math.nan
    for current in series:
        previous = (weight * current + (period - weight) * previous) / period
        output.append(previous)
    return Series(output)


def REF(value: Any, periods: int = 1) -> Series:
    series = _as_series(value)
    periods = int(periods)
    return Series([math.nan] * periods + series.values[: max(0, len(series) - periods)])


def SUM(value: Any, period: int) -> Series:
    series = _as_series(value)
    period = int(period)
    return Series(
        math.nan if index + 1 < period else sum(series.values[index - period + 1 : index + 1])
        for index in range(len(series))
    )


def HHV(value: Any, period: int) -> Series:
    return _rolling(value, period, max)


def LLV(value: Any, period: int) -> Series:
    return _rolling(value, period, min)


def STD(value: Any, period: int) -> Series:
    return _rolling(value, period, statistics.pstdev)


def ABS(value: Any) -> Series:
    series = _as_series(value)
    return Series(abs(item) for item in series)


def MAX(left: Any, right: Any) -> Series:
    return _pairwise(left, right, max)


def MIN(left: Any, right: Any) -> Series:
    return _pairwise(left, right, min)


def IF(condition: Any, when_true: Any, when_false: Any) -> Series:
    test = _as_series(condition)
    left, right = _broadcast(when_true, len(test)), _broadcast(when_false, len(test))
    return Series(a if flag else b for flag, a, b in zip(test, left, right))


def CROSS(left: Any, right: Any) -> Series:
    a, b = _as_series(left), _as_series(right)
    right_values = _broadcast(b, len(a))
    output = [0.0]
    for index in range(1, len(a)):
        output.append(1.0 if a[index] > right_values[index] and a[index - 1] <= right_values[index - 1] else 0.0)
    return Series(output)


def _series_environment(symbol: Contract, bar_type: BarType, select: int, session_type: THType) -> dict[str, Series]:
    context = get_context()
    if str(symbol) != str(context.symbol):
        raise DataUnavailableError("custom indicators support the trigger stock only")
    requested = BarType(bar_type)
    if not can_derive(context.bar_type, requested):
        raise DataUnavailableError(f"cannot derive {requested.value} from {context.bar_type.value}")
    if str(symbol).startswith("US.") and THType(session_type) != context.session_type:
        raise DataUnavailableError(
            f"requested {THType(session_type).value} but input contains {context.session_type.value}"
        )
    bars = context.bars_for(requested)
    end = len(bars) - select + 1
    bars = bars[: max(0, end)]
    return {
        "CLOSE": Series(bar.close for bar in bars),
        "OPEN": Series(bar.open for bar in bars),
        "HIGH": Series(bar.high for bar in bars),
        "LOW": Series(bar.low for bar in bars),
        "VOL": Series(bar.volume for bar in bars),
        "VOLUME": Series(bar.volume for bar in bars),
    }


def _registration(indicator_name: str, kind: str) -> dict[str, Any]:
    try:
        registration = get_context().registered_indicators[indicator_name.upper()]
    except KeyError as error:
        raise DataUnavailableError(f"indicator {indicator_name} was not registered") from error
    if registration["kind"] != kind:
        raise DataUnavailableError(
            f"indicator {indicator_name} was registered as {registration['kind']}, not {kind}"
        )
    return registration


def _statements(script: str) -> list[str]:
    cleaned = re.sub(r"\{[^}]*\}", "", script)
    return [part.strip() for part in cleaned.replace("\n", " ").split(";") if part.strip()]


def _translate_expression(expression: str) -> str:
    expression = re.split(
        r",\s*(?:COLOR|LINETHICK|NODRAW|DOTLINE|STICK|POINTDOT)",
        expression,
        flags=re.IGNORECASE,
    )[0]
    expression = re.sub(r"\bAND\b", "*", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bOR\b", "+", expression, flags=re.IGNORECASE)
    expression = expression.replace("&&", "*").replace("||", "+")
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expression))
    for name in sorted(identifiers, key=len, reverse=True):
        expression = re.sub(rf"\b{re.escape(name)}\b", name.upper(), expression)
    return expression


def _rolling(value: Any, period: int, operation: Callable[[list[float]], float]) -> Series:
    series = _as_series(value)
    period = int(period)
    return Series(
        math.nan if index + 1 < period else operation(series.values[index - period + 1 : index + 1])
        for index in range(len(series))
    )


def _as_series(value: Any) -> Series:
    if isinstance(value, Series):
        return value
    return Series([float(value)])


def _pairwise(
    left: Any, right: Any, operation: Callable[[float, float], float]
) -> Series:
    length = max(
        len(left) if isinstance(left, Series) else 1,
        len(right) if isinstance(right, Series) else 1,
    )
    return Series(
        operation(a, b)
        for a, b in zip(_broadcast(left, length), _broadcast(right, length))
    )


def _broadcast(value: Any, length: int) -> list[float]:
    if isinstance(value, Series):
        if len(value) == length:
            return value.values
        if len(value) == 1:
            return value.values * length
        raise ValueError("indicator series lengths do not match")
    return [float(value)] * length


def _last(value: Any) -> float:
    if isinstance(value, Series):
        return value[-1] if len(value) else math.nan
    return float(value)


_MYLANG_FUNCTIONS = {
    "MA": MA,
    "EMA": EMA,
    "EXPMEMA": EXPMEMA,
    "SMA": SMA,
    "REF": REF,
    "SUM": SUM,
    "HHV": HHV,
    "LLV": LLV,
    "STD": STD,
    "ABS": ABS,
    "MAX": MAX,
    "MIN": MIN,
    "IF": IF,
    "CROSS": CROSS,
}


__all__ = [
    "register_indicator",
    "register_indicator_Python",
    "get_MyLang_indicator",
    "get_Python_indicator",
]
