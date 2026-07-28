from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response, status

from .api_errors import ApiProblem
from .api_models import error_responses
from .monitoring_api_models import (
    MonitorAlert,
    MonitorAlertsResponse,
    MonitorBarsResponse,
    MonitoredInstrument,
    MonitoringDiagnosticsResponse,
    MonitoringStatusResponse,
    MonitorInstrumentRequest,
    MonitorInstrumentUpdate,
    MonitorRule,
    MonitorRuleRequest,
    MonitorRulesResponse,
    MonitorRuleUpdate,
    OptionChainResponse,
    OptionContractResponse,
    OptionExpirationsResponse,
    SnapshotResponse,
    WatchlistResponse,
)
from .monitoring_service import MonitoringService
from .opend import OpenDRequestError, OpenDUnavailableError


def create_monitoring_router(service: MonitoringService) -> APIRouter:
    router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

    @router.get("/status", response_model=MonitoringStatusResponse)
    async def monitoring_status() -> dict[str, Any]:
        return service.status()

    @router.get(
        "/diagnostics",
        response_model=MonitoringDiagnosticsResponse,
    )
    async def monitoring_diagnostics() -> dict[str, Any]:
        return await service.diagnostics()

    @router.get("/watchlist", response_model=WatchlistResponse)
    async def watchlist() -> dict[str, Any]:
        return {"instruments": service.list_instruments()}

    @router.post(
        "/watchlist",
        response_model=MonitoredInstrument,
        status_code=status.HTTP_201_CREATED,
        responses=error_responses(422),
    )
    async def add_to_watchlist(
        request: MonitorInstrumentRequest,
    ) -> dict[str, Any]:
        try:
            return service.add_instrument(request.model_dump(mode="json"))
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.patch(
        "/watchlist/{code}",
        response_model=MonitoredInstrument,
        responses=error_responses(404, 422),
    )
    async def update_watchlist_item(
        code: str,
        request: MonitorInstrumentUpdate,
    ) -> dict[str, Any]:
        try:
            return service.update_instrument(
                code,
                request.model_dump(mode="json", exclude_none=True),
            )
        except KeyError as error:
            raise _not_found("monitor_instrument_not_found", code) from error
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.delete(
        "/watchlist/{code}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=error_responses(404),
    )
    async def delete_watchlist_item(code: str) -> Response:
        try:
            service.delete_instrument(code)
        except KeyError as error:
            raise _not_found("monitor_instrument_not_found", code) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/underlyings/{code}/snapshot",
        response_model=SnapshotResponse,
        responses=error_responses(404, 422, 503),
    )
    async def underlying_snapshot(code: str) -> dict[str, Any]:
        try:
            return await service.snapshot(code)
        except KeyError as error:
            raise _not_found("monitor_snapshot_not_found", code) from error
        except ValueError as error:
            raise _invalid_request(error) from error
        except (OpenDRequestError, OpenDUnavailableError) as error:
            raise _market_data_problem(error) from error

    @router.get(
        "/underlyings/{code}/bars",
        response_model=MonitorBarsResponse,
        responses=error_responses(422, 503),
    )
    async def underlying_bars(
        code: str,
        count: int = Query(default=120, ge=2, le=1_000),
        ktype: str = Query(default="K_5M", pattern=r"^K_[A-Z0-9]+$"),
    ) -> dict[str, Any]:
        try:
            return await service.bars(code, count=count, ktype=ktype)
        except ValueError as error:
            raise _invalid_request(error) from error
        except (OpenDRequestError, OpenDUnavailableError) as error:
            raise _market_data_problem(error) from error

    @router.get(
        "/underlyings/{code}/option-expirations",
        response_model=OptionExpirationsResponse,
        responses=error_responses(422, 503),
    )
    async def option_expirations(code: str) -> dict[str, Any]:
        try:
            return await service.expirations(code)
        except ValueError as error:
            raise _invalid_request(error) from error
        except (OpenDRequestError, OpenDUnavailableError) as error:
            raise _market_data_problem(error) from error

    @router.get(
        "/underlyings/{code}/option-chain",
        response_model=OptionChainResponse,
        responses=error_responses(404, 422, 503),
    )
    async def option_chain(
        code: str,
        expiration: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ) -> dict[str, Any]:
        try:
            return await service.option_chain(code, expiration)
        except KeyError as error:
            raise _not_found("option_chain_not_found", code) from error
        except ValueError as error:
            raise _invalid_request(error) from error
        except (OpenDRequestError, OpenDUnavailableError) as error:
            raise _market_data_problem(error) from error

    @router.get(
        "/contracts/{code}",
        response_model=OptionContractResponse,
        responses=error_responses(404, 422, 503),
    )
    async def option_contract(code: str) -> dict[str, Any]:
        try:
            return await service.option_contract(code)
        except KeyError as error:
            raise _not_found("option_contract_not_found", code) from error
        except ValueError as error:
            raise _invalid_request(error) from error
        except (OpenDRequestError, OpenDUnavailableError) as error:
            raise _market_data_problem(error) from error

    @router.get("/rules", response_model=MonitorRulesResponse)
    async def monitor_rules(
        code: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        try:
            return {"rules": service.list_rules(code=code, enabled=enabled)}
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.post(
        "/rules",
        response_model=MonitorRule,
        status_code=status.HTTP_201_CREATED,
        responses=error_responses(422),
    )
    async def create_monitor_rule(
        request: MonitorRuleRequest,
    ) -> dict[str, Any]:
        try:
            return service.create_rule(request.model_dump(mode="json"))
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.patch(
        "/rules/{rule_id}",
        response_model=MonitorRule,
        responses=error_responses(404, 422),
    )
    async def update_monitor_rule(
        rule_id: str,
        request: MonitorRuleUpdate,
    ) -> dict[str, Any]:
        try:
            return service.update_rule(
                rule_id,
                request.model_dump(mode="json", exclude_none=True),
            )
        except KeyError as error:
            raise _not_found("monitor_rule_not_found", rule_id) from error
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.delete(
        "/rules/{rule_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=error_responses(404),
    )
    async def delete_monitor_rule(rule_id: str) -> Response:
        try:
            service.delete_rule(rule_id)
        except KeyError as error:
            raise _not_found("monitor_rule_not_found", rule_id) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/alerts", response_model=MonitorAlertsResponse)
    async def monitor_alerts(
        code: str | None = None,
        unacknowledged_only: bool = False,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            return service.alerts(
                code=code,
                unacknowledged_only=unacknowledged_only,
                cursor=cursor,
                limit=limit,
            )
        except ValueError as error:
            raise _invalid_request(error) from error

    @router.post(
        "/alerts/{alert_id}/ack",
        response_model=MonitorAlert,
        responses=error_responses(404),
    )
    async def acknowledge_monitor_alert(alert_id: str) -> dict[str, Any]:
        try:
            return service.acknowledge_alert(alert_id)
        except KeyError as error:
            raise _not_found("monitor_alert_not_found", alert_id) from error

    return router


def _not_found(code: str, value: str) -> ApiProblem:
    return ApiProblem(
        status_code=404,
        code=code,
        message=f"找不到监控对象：{value}",
    )


def _invalid_request(error: Exception) -> ApiProblem:
    return ApiProblem(
        status_code=422,
        code="invalid_monitoring_request",
        message=str(error),
    )


def _market_data_problem(error: Exception) -> ApiProblem:
    message = str(error)
    lowered = message.lower()
    if "permission" in lowered or "authority" in lowered:
        code = "market_data_permission_denied"
    elif "quota" in lowered or "subscription" in lowered:
        code = "market_data_quota_exhausted"
    elif "not installed" in lowered or "unavailable" in lowered:
        code = "opend_unavailable"
    else:
        code = "market_data_request_failed"
    return ApiProblem(
        status_code=503,
        code=code,
        message=message,
    )
