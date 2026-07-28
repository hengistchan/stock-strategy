import { describe, expect, it } from "vitest";
import {
  buildOptionChain,
  type OptionContractInput,
  type OptionSnapshotInput,
} from "./optionChain";

function contract(
  code: string,
  side: string,
  strike: number | string,
): OptionContractInput {
  return {
    code,
    name: code,
    underlying_code: "US.AAPL",
    option_type: side,
    expiration: "2026-07-31",
    strike_price: strike,
    lot_size: 100,
  };
}

function snapshot(
  code: string,
  values: Partial<OptionSnapshotInput> = {},
): OptionSnapshotInput {
  return {
    code,
    source_time: "2026-07-27 10:30:00",
    bid_price: 2,
    ask_price: 4,
    volume: 100,
    option_open_interest: 200,
    option_implied_volatility: 20,
    ...values,
  };
}

describe("buildOptionChain", () => {
  it("merges snapshots, pairs calls and puts, and sorts strikes stably", () => {
    const contracts = [
      contract("US.AAPL260731P105000", "PUT", 105),
      contract("US.AAPL260731C95000", "CALL", 95),
      contract("US.AAPL260731P95000", "PUT", 95),
      contract("US.AAPL260731C100000", "CALL", 100),
      contract("US.AAPL260731P100000", "PUT", 100),
      contract("US.AAPL260731C105000", "CALL", 105),
    ];
    const snapshots = contracts.map((item) =>
      snapshot(String(item.code), {
        option_delta: String(item.option_type) === "CALL" ? 0.52 : -0.48,
      }),
    );

    const model = buildOptionChain({
      contracts,
      snapshots,
      underlyingPrice: 102,
    });

    expect(model.rows.map((row) => row.strike)).toEqual([95, 100, 105]);
    expect(model.atmStrike).toBe(100);
    expect(model.rows[0].call?.code).toBe("US.AAPL260731C95000");
    expect(model.rows[0].put?.code).toBe("US.AAPL260731P95000");
    expect(model.rows[0].call?.moneyness).toBe("ITM");
    expect(model.rows[0].put?.moneyness).toBe("OTM");
    expect(model.rows[1].call?.moneyness).toBe("ATM");
    expect(model.rows[1].put?.moneyness).toBe("ATM");
    expect(model.rows[2].call?.moneyness).toBe("OTM");
    expect(model.rows[2].put?.moneyness).toBe("ITM");
    expect(model.rows[1].call).toEqual(
      expect.objectContaining({
        midPrice: 3,
        spread: 2,
        volumeOpenInterestRatio: 0.5,
        impliedVolatility: 20,
      }),
    );
    expect(model.rows[1].call?.spreadPct).toBeCloseTo(200 / 3);
  });

  it("chooses the lower strike for an equidistant ATM tie", () => {
    const model = buildOptionChain({
      contracts: [
        contract("US.AAPL260731C100000", "CALL", 100),
        contract("US.AAPL260731C105000", "CALL", 105),
      ],
      snapshots: [],
      underlyingPrice: 102.5,
    });

    expect(model.atmStrike).toBe(100);
    expect(model.rows.map((row) => row.isAtm)).toEqual([true, false]);
  });

  it("treats inverted, missing, non-finite, and N/A values as unavailable", () => {
    const model = buildOptionChain({
      contracts: [
        contract("US.AAPL260731C100000", "CALL", 100),
        contract("US.AAPL260731P100000", "PUT", 100),
        contract("US.BADTYPE", "N/A", 110),
        contract("US.BADSTRIKE", "CALL", "N/A"),
      ],
      snapshots: [
        snapshot("US.AAPL260731C100000", {
          bid_price: 5,
          ask_price: 4,
          volume: "N/A",
          option_open_interest: 0,
          option_implied_volatility: Number.NaN,
        }),
        snapshot("US.AAPL260731P100000", {
          bid_price: "N/A",
          ask_price: 4,
          volume: -1,
          option_open_interest: Number.POSITIVE_INFINITY,
        }),
      ],
      underlyingPrice: Number.NaN,
    });

    expect(model.rejectedContractCount).toBe(2);
    expect(model.atmStrike).toBeNull();
    expect(model.rows[0].call).toEqual(
      expect.objectContaining({
        quoteMarketState: "inverted",
        midPrice: null,
        spread: null,
        spreadPct: null,
        volume: null,
        volumeOpenInterestRatio: null,
        impliedVolatility: null,
        moneyness: "UNKNOWN",
      }),
    );
    expect(model.rows[0].put).toEqual(
      expect.objectContaining({
        quoteMarketState: "missing",
        midPrice: null,
        volume: null,
        openInterest: null,
      }),
    );
  });

  it("summarizes complete call and put volume and open interest", () => {
    const contracts = [
      contract("US.C95", "CALL", 95),
      contract("US.C100", "CALL", 100),
      contract("US.P95", "PUT", 95),
      contract("US.P100", "PUT", 100),
    ];
    const model = buildOptionChain({
      contracts,
      snapshots: [
        snapshot("US.C95", { volume: 100, option_open_interest: 200 }),
        snapshot("US.C100", { volume: 50, option_open_interest: 100 }),
        snapshot("US.P95", { volume: 50, option_open_interest: 75 }),
        snapshot("US.P100", { volume: 25, option_open_interest: 75 }),
      ],
      underlyingPrice: 100,
    });

    expect(model.summary.call).toEqual({
      contractCount: 2,
      totalVolume: 150,
      totalOpenInterest: 300,
      volumeObservedContracts: 2,
      openInterestObservedContracts: 2,
      volumeComplete: true,
      openInterestComplete: true,
    });
    expect(model.summary.put.totalVolume).toBe(75);
    expect(model.summary.put.totalOpenInterest).toBe(150);
    expect(model.summary.callPutVolumeRatio).toBe(2);
    expect(model.summary.callPutOpenInterestRatio).toBe(2);
  });

  it("does not publish ratios from incomplete or zero-denominator aggregates", () => {
    const model = buildOptionChain({
      contracts: [
        contract("US.C100", "CALL", 100),
        contract("US.P100", "PUT", 100),
      ],
      snapshots: [
        snapshot("US.C100", { volume: 100, option_open_interest: 200 }),
        snapshot("US.P100", { volume: "N/A", option_open_interest: 0 }),
      ],
      underlyingPrice: 100,
    });

    expect(model.summary.put.totalVolume).toBeNull();
    expect(model.summary.put.volumeComplete).toBe(false);
    expect(model.summary.callPutVolumeRatio).toBeNull();
    expect(model.summary.callPutOpenInterestRatio).toBeNull();
  });

  it("keeps the first duplicate side deterministically and handles an empty chain", () => {
    const duplicate = buildOptionChain({
      contracts: [
        contract("US.FIRST", "CALL", 100),
        contract("US.SECOND", "CALL", 100),
      ],
      snapshots: [],
      underlyingPrice: 100,
    });
    const empty = buildOptionChain({
      contracts: [],
      snapshots: [snapshot("US.ORPHAN")],
      underlyingPrice: 100,
    });

    expect(duplicate.rows[0].call?.code).toBe("US.FIRST");
    expect(duplicate.duplicateContractCount).toBe(1);
    expect(empty).toEqual(
      expect.objectContaining({
        rows: [],
        atmStrike: null,
        rejectedContractCount: 0,
        duplicateContractCount: 0,
      }),
    );
    expect(empty.summary.callPutVolumeRatio).toBeNull();
    expect(empty.summary.call.totalVolume).toBeNull();
  });
});
