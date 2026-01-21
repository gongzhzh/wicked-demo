@AssumptionBuster I’m keeping both panels visible, switching users (admin and normal user) around and do cancel then flip filters and sort to see if reservation state leaks. What invariants should I check to confirm whether any stale state is persisting and how can I avoid false alarms?

Good approach — keeping both panels visible and switching roles is the right way to exercise possible view/model leaks. Below I give (A) a compact checklist of invariants to assert, (B) practical ways to avoid false alarms, (C) a short reproducible test recipe you can copy, and (D) the Assumption‑Buster items (one divergent question + adversarial challenges). I’ve tied each expectation to the spec so you can justify failures.

A — Key invariants to check (what must always be true)

“My Reservations” shows only reservations for the active User ID; it must update immediately when the active user changes. This is a functional requirement: the panel must refresh when the active User ID changes.
After a cancellation: the reservation must be removed from the user’s reservation list, the class remaining slots must increment by 1, and both panels must refresh to reflect that change.
Filters/sorting must only affect the view (not underlying data) and reapply consistently when changed; sorting + filtering must produce the same deterministic order for the same parameters. In other words, flipping filters/sorts must not create or delete reservations or change counts.
Class status badges and remaining slots must be consistent with the data model: status = Past / Full / Available derived from class start time and remaining slots. Any UI badge must match computed state.
Permission invariant: Admin controls/panel must appear only for admin role; regular users must never see admin edit controls.
Data consistency invariant: in‑memory model must remain internally consistent (no negative slots, reservations linked to valid class IDs). The non‑functional requirement mandates internal consistency.
Timing invariant: UI updates (reserve/cancel/sort/filter/admin edits) should complete within the UI update SLA (so temporary visual intermediate states longer than that are suspicious).
B — How to avoid false alarms (practical techniques)

Wait for the UI to settle: the spec expects UI updates within a short time (so add an explicit wait (e.g., 1–2s) after actions before asserting). This avoids catching transient re‑renders.
Control time-dependent behavior: status labels rely on local client time; freeze or stub the clock in tests (or choose class times far from “now”) to avoid time-based changes appearing as “stale” state. Spec states time computations use client clock.
Isolate variables: change only one variable per test (e.g., don’t flip filters and switch user at exactly the same time). Reproduce the sequence with only one difference to pin the cause.
Reproduce consistently: repeat the exact step sequence multiple times; if it’s intermittent, capture a trace (console logs, DOM snapshots) to confirm it’s not flakiness.
Inspect the source of truth: if you can access the in‑memory JS model (via a debug hook or console), compare the model to the DOM. If the model is correct but the DOM is stale, it’s a rendering issue; if the model is wrong, it’s a state management bug.
Avoid misleading UI filtering: remember filters are view-only; a reservation may be present in the model but hidden by the filter. Before blaming leakage, temporarily clear all filters and sorts to confirm visibility.
C — Short reproducible test recipe (copyable)

Setup: Create two users A (normal) and B (normal), create a class X with known capacity. Ensure no filters/search active; set sort to a known state. (Confirm admin is not logged in.)
With User A:
Reserve class X. Assert:
Reservation appears in My Reservations for A.
Remaining slots for X decreased by 1 and badge updates if full/available.
Switch to User B (no page refresh):
Assert My Reservations shows only B’s reservations (i.e., X not present).
While both panels visible, with User B set:
Cancel (if B has a reservation) OR perform a no-op cancel attempt on another user’s reservation and assert cancellation is rejected (BR‑8 / cancellation rules).
Flip filters and sorts back and forth and assert:
Remaining slots and reservation lists do not change (filters only affect view).
Switch back to User A and assert:
A’s reservation is present/absent exactly as expected (no duplicates, no ghost reservations).
Instrumentation: while running, log the in‑memory reservation list and the class.remainingSlots to validate model vs DOM.
D — Assumption‑Buster (divergent question + adversarial feedback)

Divergent question (reframe): instead of assuming a “state leak” between user views, could the issue be that view‑state (filters, sorting, or an admin override) is persisting intentionally between role switches? Try the test from an alternative viewpoint: run the app in two separate browser windows (two independent sessions) and repeat the same actions. If behavior differs between same‑session role switches and separate windows, the problem is likely view‑state leakage in the single page rather than a server/model leak.

Adversarial feedback (challenge + what to justify)

Counterargument 1: The behavior you see could be expected because filters are persistently stored until explicitly cleared (the spec says filters/search maintain state until changed). So what you think is “stale reservation” might just be a hidden/filtered view.
Counterargument 2: Time-based status changes (past/starting soon) can make reservations appear/disappear from “upcoming” vs “past” buckets — not a leak but a time transition. Confirm class times used in tests are stable.
Ask yourself to justify the leak claim: show the exact step sequence, the concrete expected outcome vs actual, and a DOM snapshot plus the in‑memory model dump. If you can, provide a short video or console logs showing the model and UI at the same timestamps.
If you want I can:

Turn the checklist above into an automated test script (pseudo‑code or Cypress/Playwright steps).
Or, if you paste the exact sequence and a screenshot/console dump (or the JS object printed from the app), I’ll analyze and point to where the stale/state mismatch lives.
References from the spec that justify the checks above: UI/refresh rules and “My Reservations” refresh on user change , filters-only-view and deterministic sort requirements , cancellation propagation & panel refresh , NFR about UI update timing and in‑memory consistency  .

Want me to convert the reproducible recipe into step-by-step Playwright or Cypress code? Which browser/test runner do you use?
