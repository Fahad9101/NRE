import { pathToFileURL } from "node:url";

const endpoint = "wss://stream.data.alpaca.markets/v2/sip";
const symbols = { IBM: { venue: "N", tape: "A" }, AAPL: { venue: "Q", tape: "C" } };

export function openingStatus(trade, received, opening) {
  const listing = symbols[trade.S];
  if (trade.T !== "t" || !listing || trade.x !== listing.venue ||
      trade.z !== listing.tape || !Array.isArray(trade.c) || !trade.c.includes("Q")) return null;
  const published = Date.parse(trade.t);
  if (!Number.isFinite(published) || published < opening || received < published ||
      received > opening + 60_000 || received - published > 5_000) return "outside_timing_limits";
  return "observed";
}

function plannedOpening() {
  // One fixed preflight session outside the 2027 research cohort.
  return Date.parse("2026-11-16T14:30:00Z");
}

function probe(mode, key, secret) {
  const opening = plannedOpening();
  if (mode === "opening" &&
      (Date.now() < opening - 300_000 || Date.now() > opening - 5_000)) {
    return Promise.resolve({ status: "outside_preflight_window" });
  }
  return new Promise((resolve) => {
    const socket = new WebSocket(endpoint);
    const counts = Object.fromEntries(Object.keys(symbols).map(s => [s, {
      observed: 0, outside_timing_limits: 0,
    }]));
    let authenticated = false;
    let subscribed = false;
    let timer;
    let done = false;

    function finish(status, providerCode) {
      if (done) return;
      done = true;
      clearTimeout(timer);
      socket.close();
      resolve({ status, authenticated, subscribed, ...(providerCode === undefined ? {} : { providerCode }),
                ...(mode === "opening" ? { counts, receiverClockVerified: false } : {}) });
    }

    timer = setTimeout(() => finish("connection_timeout"), 15_000);
    socket.addEventListener("error", () => finish("connection_error"));
    socket.addEventListener("close", () => finish("closed_early"));
    socket.addEventListener("message", event => {
      const received = Date.now();
      try {
        for (const message of JSON.parse(event.data)) {
          if (message.T === "error") {
            finish("provider_error", Number.isInteger(message.code) ? message.code : undefined);
          } else if (message.T === "success" && message.msg === "connected") {
            socket.send(JSON.stringify({ action: "auth", key, secret }));
          } else if (message.T === "success" && message.msg === "authenticated") {
            authenticated = true;
            if (mode === "entitlement") return finish("entitled");
            socket.send(JSON.stringify({ action: "subscribe", trades: Object.keys(symbols) }));
          } else if (message.T === "subscription" && authenticated &&
                     Object.keys(symbols).every(symbol => message.trades?.includes(symbol))) {
            subscribed = true;
            clearTimeout(timer);
            timer = setTimeout(() => finish("sample_complete"), Math.max(0, opening + 60_000 - Date.now()));
          } else if (subscribed) {
            const status = openingStatus(message, received, opening);
            if (status !== null && received <= opening + 60_000) counts[message.S][status]++;
          }
        }
      } catch {
        finish("invalid_message");
      }
    });
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const mode = process.argv[2];
  try {
    const { APCA_API_KEY_ID: key, APCA_API_SECRET_KEY: secret } = process.env;
    if (!key || !secret || !["entitlement", "opening"].includes(mode)) throw new Error();
    const result = await probe(mode, key, secret);
    console.log(JSON.stringify({ mode, ...result }));
  } catch {
    console.log(JSON.stringify({ mode, status: "probe_error" }));
    process.exitCode = 2;
  }
}
