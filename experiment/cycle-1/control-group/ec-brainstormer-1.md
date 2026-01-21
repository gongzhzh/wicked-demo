@Brainstormer What are the core rules to follow or states to focus when test a race condition in a multi-user book/cancel situation?

Nice focus — testing race conditions in book/cancel flows is exactly where invariants and timing windows catch bugs. Below I’ll (A) list the core invariants/rules to assert, (B) the important runtime states to watch, and (C) concrete race scenarios and checks to run. I’ll also give a few cross-domain hints to stimulate test ideas.

A. Core rules / invariants to enforce and assert

Do not allow reservations when remaining slots = 0 (class must be Full). This is a hard business rule to enforce under concurrency.
Cancelling a reservation must remove the reservation and increase remaining slots by exactly 1. The UI must refresh to reflect that change.
Remaining slots / capacity must never go negative and should never exceed capacity under correct operation. Use this as a primary invariant check.
Users may only cancel their own reservations; cancellations for past classes or within the 1‑hour cutoff must be rejected. Those checks must still hold when concurrent actions occur.
Reservation meta-rules (no double booking at same time; max 3 future reservations) must be enforced atomically with the slot decrement.
B. Runtime states to focus on during tests

remainingSlots (numeric) — the single most important value for races.
Reservation existence (per user): whether a given reservation record exists for a user/class.
Class status badge (Available / Full / Past) — ensure it reflects remainingSlots/time.
UI panels: “Available Classes” and “My Reservations” and the message area — test whether they refresh and show correct messages.
System time dependency / clock: the app uses client local time for past/future and 1‑hour rules — clock skew between clients/tabs is a test factor.
C. Concrete race scenarios (how to run + what to assert)

Last‑seat duel (classic)
Setup: remainingSlots = 1. Two different user sessions (different browsers/tabs/users) press Reserve “at the same time” (simulate near-simultaneous requests).
Expectation/assertions:
Exactly one succeeds and creates a reservation for its user.
remainingSlots becomes 0, status becomes Full.
The losing attempt is rejected with a clear error (full class).
No negative remainingSlots and total reservedCount + remainingSlots == capacity. (Use this conservation invariant.)
2. Cancel + Reserve race

Setup: User A cancels while User B reserves concurrently.
Variants: cancel processed first vs reserve processed first.
Expectation/assertions:
Final reserved count and remainingSlots are consistent with one cancel and one reserve (net zero change) or with whichever action won ordering.
If cancel is rejected (past/within 1 hour), reserve must reflect the correct slots.
3. Rapid repeated toggles (flapping)

Rapidly alternate reserve and cancel (multiple clients) to try to force off‑by‑one or negative values.
Expectation: remainingSlots stays within [0, capacity] and UI converges (within the 1s UI update NFR) to the correct state.
4. Same‑user multi‑tab / stale UI

Same User ID in two tabs: reserve in tab A, reserve in tab B (or cancel in one tab). Because data is in‑memory and UI refresh rules apply, test whether tab B’s view becomes stale or allows invalid actions. Assert actions are disabled when no User ID is set and that the message area shows correct errors/successes.
5. Admin edits during concurrent actions

Admin increases/decreases capacity or overrides status while users try to reserve/cancel.
Expectation: edits should propagate to both panels and invariants must hold (no negative slots, reservedCount consistent).
6. Time‑window edge cases

Cancel attempts exactly at the 1‑hour cutoff, or with client clocks intentionally skewed. Because the system uses client local clock, test different client clock offsets to see whether inconsistent outcomes occur.
D. Checks, oracles, and instrumentation to add to tests

Conservation oracle: capacity == remainingSlots + countOfReservationsForClass. Check after every concurrent operation. This will detect lost updates or double‑bookings quickly.
Non‑negative oracle: assert remainingSlots >= 0 and <= capacity.
Ownership oracle: a cancellation results in removal only when UserID matches; otherwise reject.
UI sync oracle: after an operation, both panels and the status badge must reflect the change within the UI update SLA (1s). Report inconsistencies as errors.
Error message oracle: rejected operations must return a clear error indicating the rule violated (full class / past class / within 1 hour / not owner).
E. Cross‑domain associations & test heuristics (quick inspiration)

Treat seats like bank balances: reservations are withdrawals and cancellations are deposits — look for lost updates and race conditions identical to concurrent debit/credit bugs. Use a “ledger” invariant (sum of balances) to detect errors.
Think of it like semaphore tokens: acquiring a token (reserve) must be atomic; releasing (cancel) returns it. Test acquire/release sequences under contention.
F. Practical tips for executing tests

Use separate browser processes/containers to simulate independent client clocks and memory spaces (important because constraints say logic runs client‑side, in‑memory).
Introduce synthetic delays in the action handlers (or in your test harness) to widen the concurrency window and expose races.
Log/timestamp every action (with client clock and test‑harness clock) so you can reconstruct orderings when a failure appears.
Run many randomized repeats (fuzzing): random user IDs, random small delays, admin edits interleaved. Race bugs are often probabilistic.
If you want, I can:

Draft a short checklist of concrete step‑by‑step test scripts for the top 6 scenarios above, or
Produce a small test harness script outline (how to run parallel browser sessions or use puppeteer/playwright to provoke races).
Which would help you most right now?
