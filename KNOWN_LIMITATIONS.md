# Known limitations of the gate described in TR-2026-01 (as of run 6, commit 3e7351b)

These are the limitations the report itself states. They are listed here so that the repository carries the same "known limitations" text as the report at release.

1. **Person-exposure false passes remain at 8** (of 23 false passes in 280 hazardous commands under a stale replica). Four of them are motor-start commands that passed while an interlock had been removed; these do not close by rule changes.
2. **Behavioral equivalence cannot see dormant logic changes.** A change to a rung that has not executed does not appear in behaviour. A static program-signature check must precede any behavioral check.
3. **On Modbus there is no program signature**, so the gate cannot see this class of change on that protocol; PLC write protection and change management must be in place.
4. **The gate blocks some safe-direction commands.** 2 of 94 stop/de-energise commands were blocked because the loaded state already violated a rule. Category safety stops must be wired around the gate.
5. **A sub-second input change can hold the gate in suspicion** (16 of 25 live-staged rows blocked at 0.07–0.3 s hold); the recovery interval has a lower bound of 8 s and no upper bound, and has not yet been measured.
6. **Three hazard kinds (34 test commands) are confirmed unblockable** by the gate: remote reset, remote acknowledge (the gate cannot tell a supervisory write from an operator press) and 32-bit setpoints written as two words.
7. **Scope of evidence**: simulated PLC assembled from product components, three self-authored ladders (3–19 rungs), one machine, no externally authored program, no physical PLC comparison, labels assigned by the team that built the gate.
