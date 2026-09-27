# FleetFlight CLI: demo transcripts (MOCKED output)

All numbers are illustrative. `core-ref` is our reference model, not Base Gen 3.

---

## 1. The normal test passes

```
$ fleetflight sim --model core-ref --scenario bms-fault-basic --seed 1
core-ref · hub-manager-ref@v0.3.1 · seed 1 · horizon 4000 ms

  t(ms)  event               bms       hub      inverter      note
      0  init                HEALTHY   ONLINE   DISCHARGING   seq41 5.0 kW
    100  bms_fault*          FAULTED   ONLINE   DISCHARGING   m_fault → hub (400 ms)
    500  deliver m_fault     FAULTED   ONLINE   DISCHARGING   hub → inv STOP
    550  deliver STOP        FAULTED   ONLINE   SHUTDOWN

  I1 FAULT_SHUTDOWN_BOUNDED     PASS   (fault→shutdown 450 ms ≤ 500 ms)
  I2..I5                        PASS
  * = injected
```

> "Great, it passes. But that's one ordering. Does it hold for *every* ordering?"

---

## 2. Exhaustive check finds a counterexample

```
$ fleetflight check --model core-ref --sut hub-manager-ref@v0.3.1
core-ref · depth ≤ 40 ticks (4 s) · ≤ 3 injections · BFS

ASSUMPTIONS
  · bus.latency_ms ≤ 800; may delay, drop, duplicate, reorder
  · BMS FAULT edge-triggered; heartbeat 2000 ms
  · inverter holds setpoint 1000 ms w/o command, then IDLE
  · hardware interlocks OUT OF SCOPE

exploring ████████████████████████████ 1,284,511 states · 3.90M transitions · 41.2 s

  I1 FAULT_SHUTDOWN_BOUNDED       FAIL   cex-0017  (minimal, 6 steps)
  I2 NO_HIGH_POWER_WHEN_UNKNOWN   PASS
  I3 NO_RESURRECTED_COMMANDS      PASS
  I4 IDEMPOTENT_COMMANDS          PASS
  I5 COMMS_LOSS_SAFE_FALLBACK     PASS

1 invariant violated. Wrote out/cex-0017.json
```

---

## 3. Explain the counterexample

```
$ fleetflight explain cex-0017
I1 FAULT_SHUTDOWN_BOUNDED violated at t=700 ms (BMS faulted 600 ms, inverter still discharging)

  #  t(ms)  event                 bms      hub         inverter      bus
  0      0  init                  HEALTHY  ONLINE      DISCHARGING   –
  1    100  bms_fault*            FAULTED  ONLINE      DISCHARGING   m_fault(bms→hub)
  2    100  bus_delay* +400ms     FAULTED  ONLINE      DISCHARGING   m_fault @500
  3    200  hub_restart*          FAULTED  RESTARTING  DISCHARGING   m_fault DROPPED (RX buffer cleared)
  4    600  hub_boot_complete     FAULTED  ONLINE      DISCHARGING   m_resume(seq41 from NVM)
  5    650  deliver m_resume      FAULTED  ONLINE      DISCHARGING   inverter watchdog refreshed
  6    700  ✗ VIOLATION           FAULTED  ONLINE      DISCHARGING   600 ms > 500 ms

Root pattern: fault signal is edge-triggered and volatile; restart recovery trusts NVM.
Earliest point the hub could have known: never before the next BMS heartbeat (t=2100).
```

---

## 4. Replay in the executable simulator (same event list, not a re-translation)

```
$ fleetflight replay --counterexample cex-0017
replaying cex-0017 against hub-manager-ref@v0.3.1 · seed 8841
  steps 0–6 match model trace          ✓
  trace hash sha256:3f0a77c2e519       ✓ (identical to checker)
  I1 FAULT_SHUTDOWN_BOUNDED            FAIL at t=700 ms
```

Run it 100 times: same hash every time. That's the "deterministic" claim, shown, not asserted.

```
$ fleetflight replay --counterexample cex-0017 --repeat 100 | uniq -c
    100 sha256:3f0a77c2e519 FAIL
```

---

## 5. Fix, then replay the exact same sequence

**Fix A (hub-side):** boot into `DEGRADED`, drop NVM command, send `STOP` on boot.

```
$ fleetflight replay --counterexample cex-0017 --sut hub-manager-ref@v0.3.2
  #  t(ms)  event                 bms      hub         inverter
  3    200  hub_restart*          FAULTED  RESTARTING  DISCHARGING
  4    600  hub_boot_complete     FAULTED  DEGRADED    DISCHARGING   boot: STOP epoch=2
  5    650  deliver STOP          FAULTED  DEGRADED    SHUTDOWN
  I1 FAULT_SHUTDOWN_BOUNDED            FAIL  fault→shutdown 550 ms > 500 ms
```

The resurrection is gone, but the same sequence still fails: the hub's 400 ms boot eats the budget.
No hub-side change can fix that. Safety can't depend on a component that can restart.

**Fix B (local fallback):** inverter goes `SHUTDOWN` after 200 ms without a hub heartbeat,
instead of holding its setpoint for 1 s.

```
$ fleetflight replay --counterexample cex-0017 --sut hub-manager-ref@v0.3.3
  3    200  hub_restart*          FAULTED  RESTARTING  DISCHARGING
  4    400  inv hub-loss timeout  FAULTED  RESTARTING  SHUTDOWN
  5    600  hub_boot_complete     FAULTED  DEGRADED    SHUTDOWN      awaiting BMS status
  I1 FAULT_SHUTDOWN_BOUNDED            PASS  fault→shutdown 300 ms

$ fleetflight check --model core-ref --sut hub-manager-ref@v0.3.3
exploring ████████████████████████████ 1,301,877 states · 3.97M transitions · 43.0 s
  I1..I5                          PASS   (I1 worst case 300 ms)
  TRADE-OFF  every hub restart now idles the inverter ~400 ms (dispatch availability −)
```

> Design note for the video: "fix → still fails → real fix" is the strongest 60 seconds we have.
> The tool catches our own half-fix and lands on an architectural rule, and it surfaces the
> availability cost of that rule instead of hiding it.

---

## 6. Counterexample becomes a regression test

```
$ fleetflight regress --from cex-0017
wrote tests/regress/test_cex_0017.py

$ pytest tests/regress -q
.                                                         [100%]
1 passed in 0.18s
```

---

## 7. CI (GitHub check on a firmware PR)

```
fleetflight-verify / regress   ✓  23 counterexamples replayed      7 s
fleetflight-verify / check     ✓  5 invariants · 1.30M states      44 s
```

---

## Stretch: fleet

```
$ fleetflight fleet --core core-ref@v0.3.3 --n 500 --seed 8841 --inject "hub_restart:rate=0.02/min"
500 Virtual Cores · 30 min sim · 2,114 injected faults
  F1 FLEET_DISPATCH_WITHIN_AVAILABLE    PASS
  F2 NO_DISPATCH_TO_STALE_DEVICES       FAIL  seed 8841 · core #007 · t=14:32.100
```
