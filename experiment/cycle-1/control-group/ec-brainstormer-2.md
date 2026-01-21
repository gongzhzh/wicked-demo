@Brainstormer What are the core rules to follow or states to focus when test a race condition in a multi-user book/cancel situation?

Nice question — testing race conditions in book/cancel flows is exactly where bugs that break core invariants (like slot counts) hide. Your instinct to think in terms of “rules” and “states” is the right starting point.

Quick caveat from the spec first: this app is defined to run entirely client‑side with in‑memory data and no backend, and a page refresh resets state, so true multi‑process/shared‑database concurrency won’t exist unless you change the architecture. Keep that in mind when designing tests or simulating “multi‑user” behavior . Also note the business rules you must preserve: reservations cannot be created for full or past classes, cancellations are blocked within 1 hour of start, reservations are tied to the active User ID, and slot updates + status recalculation are required when reserving/cancelling .

Core rules to follow when testing race conditions

Preserve invariants (must never be violated):
Remaining slots must never go negative and must reflect actual reservations (NFR-7) .
A reservation must be stored with the creating User ID (FR-4) and cancellations must only remove that user’s reservation (BR-8) .
Class status badges must be recalculated after any change (FR-24, FR-31) .
Atomicity & isolation expectations:
Treat a reserve/cancel action as an atomic operation that either completes and updates slots/status, or is rejected and leaves state unchanged.
Concurrent attempts affecting the same slot(s) must be resolved so only valid outcomes occur (e.g., two reserves for the last slot => one succeeds, the other is rejected).
Validate business-rule guards at the moment of commit:
Re-check “not full”, “not past”, “not within 1 hour”, and “user not double-booked/max reservations” when completing the operation, not just when initiating it (BR-1, BR-2, BR-3, BR-4, BR-6, BR-7) .
Idempotency & safe retries:
The system should handle duplicate/near-duplicate requests (e.g., user double-clicking) without corrupting state (no double decrement).
Clear failure semantics:
When an action is rejected due to rules or contention, produce a clear error message and leave the system consistent (FR-25, FR-32) .
States and transitions to focus on

Key states for a class/reservation:
Class: Available (slots>0), Full (slots=0), Starting Soon (within 1 hour), Past (start < now) .
Reservation: Pending/in-flight (operation in progress), Confirmed, Cancelled, Rejected.
Transitions to watch carefully:
Available -> Full (concurrent reserves on last slot).
Full -> Available (concurrent cancel + reserve race).
Confirmed -> Cancelled (user cancels while another user is trying to reserve).
Any state -> Past/StartingSoon (when time boundary crosses; combined with in-flight ops) — note system uses client clock for these computations (C-3) .
Concrete race test scenarios (what to do and what to assert)

Two users reserve the last slot (remaining slots = 1)
Steps: Set User A and User B in two clients (or simulate sequentially but tightly timed). Both click Reserve near-simultaneously.
Expect: Exactly one reservation created, remaining slots = 0, class status = Full, the losing request shows a rejection explaining class is full. Invariants hold (no negative slots).
Spec tie-ins: remaining slots update and status recalculation on accepted reservation (FR-24), cannot reserve when slots=0 (BR-2) .
Cancel vs Reserve racing on single freed slot
Steps: Class is Full. User A cancels, User B issues Reserve at approximately same time.
Expect: Either (a) cancel completes then reserve consumes the freed slot (ending Full or Available depending on count), or (b) reserve completes then cancel still increases remaining slots by 1 (but not beyond capacity) — but overall seat counts and reservation lists must stay consistent and not allow duplication. Decide desired tie-breaker and assert it.
Assert: No negative slots; reservation ownership remains correct; UI panels refresh to reflect changes (FR-31).
Double cancel or double reserve from same user (duplicate submissions)
Steps: Click Cancel twice (or send duplicate reserve requests).
Expect: Second attempt is rejected or no-op; no double cancellation/reservation; invariants preserved (no negative slots or duplicate reservation entries).
Cancellation within 1-hour window vs simultaneous admin override
Steps: Attempt cancel within 1 hour (should be rejected). Simultaneously admin overrides capacity/status.
Expect: Business rule (BR-7) should block the cancel unless admin override explicitly allows it; verify admin actions propagate to panels (FR-31, FR-40) .
Time boundary crossing with in-flight ops
Steps: Start a reserve/cancel just before the 1-hour-before cutoff or class start, then move clock forward (or wait) so the class becomes Starting Soon/Past while the operation is in flight.
Expect: The commit logic must check the current time at commit and enforce rules (e.g., reject cancel if now within 1 hour) — because spec uses client clock, test should simulate this (C-3) .
Admin edits capacity while users reserve/cancel
Steps: Admin increases/decreases capacity while multiple users attempt to reserve.
Expect: Capacity/remaining slots must stay consistent after edits; reservations should obey updated capacity and status recalculation must run (FR-35, FR-31) .
Cross‑domain ideas (to inspire mechanisms & tests)

Optimistic concurrency (version/check‑and‑set): treat reserve/cancel as compare-and-swap on a class version — simulate races where the version has changed and assert the operation fails and is retried.
Transactional/lock semantics: think like a DB transaction — test atomic commit/rollback behaviors by aborting mid-action in tests.
Idempotency tokens: emulate duplicate client requests and ensure server/client logic is idempotent.
Event sourcing: record events (ReserveRequested, ReserveConfirmed, CancelRequested, CancelConfirmed) and assert that event replay yields the same final state. These bring useful test heuristics: inject delay between “check” and “commit” to provoke TOCTOU (time of check to time of use) races; assert socket/logged events show intended order.
Practical hints for running tests

If app is truly client-only, simulate multi-user by running multiple browser instances or automating sequences that interleave actions with controlled delays.
Instrument timestamps and a small test harness that can repeatedly try concurrent sequences to increase chance of hitting races.
Log pre- and post-state snapshots for class (capacity, remaining slots, reservations list) and assert invariants after each scenario: (sum of current reservations) + remaining slots == capacity, remaining slots >= 0, and no duplicate reservations for same user/time.
Automate repeats and randomize timing (fuzz the interleaving) — race bugs are often intermittent.
Watch for UI timing requirements (NFR-4) — UI updates should be visible within 1 second; verify the UI reflects backend/client state after each operation .
Short checklist you can copy to tests

Re-check business rules at commit time (not just at button click) .
Assert remaining slots never negative; recompute from reservations to confirm consistency (NFR-7) .
Verify reservation ownership and that cancels affect only the owner (BR-8) .
Verify status badges update whenever slots/reservations change (FR-24, FR-31) .
Check messages for clear error/explanations on rejects (FR-25, FR-32) .
If you want, I can:

Draft a small set of runnable automation scripts (Selenium / Playwright) that simulate the specific race cases above, or
Map these scenarios to a concise test matrix with preconditions / steps / expected results / assertions.
Which would help more right now?
