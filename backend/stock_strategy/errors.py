from __future__ import annotations

from .models import ErrCode


class APIException(Exception):
    """Futu-compatible strategy exception carrying a documented error code."""

    def __init__(self, message: str, err_code: ErrCode = ErrCode.ReqFailed) -> None:
        super().__init__(message)
        self.err_code = ErrCode(err_code)


class UnsupportedAPIError(APIException, NotImplementedError):
    """The manual API cannot be simulated by the configured backtest model."""

    def __init__(
        self, message: str, err_code: ErrCode = ErrCode.InvalidArgument
    ) -> None:
        super().__init__(message, err_code)


class DataUnavailableError(UnsupportedAPIError, LookupError):
    """The API is supported but required point-in-time OpenD data is missing."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrCode.NoDataAvailable)
