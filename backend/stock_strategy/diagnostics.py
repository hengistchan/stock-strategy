from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import socket
import sys
from typing import Callable, Literal

from .opend import OpenDSymbolDirectory


DiagnosticStatus = Literal["pass", "fail", "blocked"]


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    id: str
    status: DiagnosticStatus
    detail: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsReport:
    ready: bool
    host: str
    port: int
    checks: tuple[DiagnosticCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "host": self.host,
            "port": self.port,
            "checks": [asdict(check) for check in self.checks],
        }


def is_opend_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


class DiagnosticsService:
    """Run the same local readiness checks for the CLI and HTTP API."""

    def __init__(
        self,
        project_root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        connection_probe: Callable[[str, int], bool] = is_opend_available,
        package_version_probe: Callable[[str], str] = version,
        quote_probe: Callable[[], str] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.host = host
        self.port = port
        self.connection_probe = connection_probe
        self.package_version_probe = package_version_probe
        self.quote_probe = quote_probe or self._default_quote_probe

    def run(self) -> DiagnosticsReport:
        checks: list[DiagnosticCheck] = [self._check_python()]
        futu_check = self._check_futu_api()
        checks.append(futu_check)
        checks.append(self._check_workspace())
        opend_check = self._check_opend()
        checks.append(opend_check)
        checks.append(self._check_quote_directory(futu_check, opend_check))
        return DiagnosticsReport(
            ready=all(check.status == "pass" for check in checks),
            host=self.host,
            port=self.port,
            checks=tuple(checks),
        )

    def _check_python(self) -> DiagnosticCheck:
        detail = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 11):
            return DiagnosticCheck("python", "pass", detail)
        return DiagnosticCheck(
            "python",
            "fail",
            detail,
            "Install Python 3.11 or newer and recreate .venv.",
        )

    def _check_futu_api(self) -> DiagnosticCheck:
        try:
            installed = self.package_version_probe("futu-api")
        except PackageNotFoundError:
            return DiagnosticCheck(
                "futu_api",
                "fail",
                "futu-api is not installed",
                "Run make install to install the OpenD dependencies.",
            )
        except Exception as error:  # pragma: no cover - defensive adapter boundary
            return DiagnosticCheck(
                "futu_api",
                "fail",
                f"Unable to inspect futu-api: {error}",
                "Reinstall the project dependencies with make install.",
            )
        return DiagnosticCheck("futu_api", "pass", f"futu-api {installed}")

    def _check_workspace(self) -> DiagnosticCheck:
        problems: list[str] = []
        generated: list[str] = []
        for name, access, access_copy in (
            ("examples", os.R_OK, "readable"),
            ("strategies", os.R_OK | os.W_OK, "readable and writable"),
        ):
            path = self.project_root / name
            if not path.is_dir():
                problems.append(f"{name}/ missing")
            elif not os.access(path, access):
                problems.append(f"{name}/ is not {access_copy}")
        for name in ("data", "runs"):
            path = self.project_root / name
            if not path.exists():
                if os.access(self.project_root, os.W_OK):
                    generated.append(f"{name}/")
                else:
                    problems.append(f"{name}/ cannot be created")
            elif not path.is_dir() or not os.access(path, os.R_OK | os.W_OK):
                problems.append(f"{name}/ is not readable and writable")
        if problems:
            return DiagnosticCheck(
                "workspace",
                "fail",
                "; ".join(problems),
                "Restore the project directories and grant the current user read/write access.",
            )
        detail = f"{self.project_root} · workspace ready"
        if generated:
            detail += f" · will create {', '.join(generated)} on first run"
        return DiagnosticCheck(
            "workspace",
            "pass",
            detail,
        )

    def _check_opend(self) -> DiagnosticCheck:
        try:
            connected = self.connection_probe(self.host, self.port)
        except OSError as error:
            connected = False
            detail = f"Connection probe failed: {error}"
        else:
            detail = (
                f"OpenD TCP reachable at {self.host}:{self.port}"
                if connected
                else f"OpenD is unreachable at {self.host}:{self.port}"
            )
        if connected:
            return DiagnosticCheck("opend", "pass", detail)
        return DiagnosticCheck(
            "opend",
            "fail",
            detail,
            "Start OpenD and verify OPEND_HOST and OPEND_PORT.",
        )

    def _check_quote_directory(
        self,
        futu_check: DiagnosticCheck,
        opend_check: DiagnosticCheck,
    ) -> DiagnosticCheck:
        if futu_check.status != "pass" or opend_check.status != "pass":
            return DiagnosticCheck(
                "quote_directory",
                "blocked",
                "Quote directory check requires futu-api and an OpenD connection",
                "Resolve the failed prerequisite, then run diagnostics again.",
            )
        try:
            detail = self.quote_probe()
        except Exception as error:
            return DiagnosticCheck(
                "quote_directory",
                "fail",
                f"OpenD quote directory request failed: {error}",
                "Unlock quote access in OpenD and confirm US/HK stock permissions.",
            )
        return DiagnosticCheck("quote_directory", "pass", detail)

    def _default_quote_probe(self) -> str:
        directory = OpenDSymbolDirectory(host=self.host, port=self.port)
        matches = directory.search("AAPL", 1)
        return f"OpenD stock directory readable · {len(matches)} probe result(s)"
