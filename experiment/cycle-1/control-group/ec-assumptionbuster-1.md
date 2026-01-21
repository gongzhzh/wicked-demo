@AssumptionBuster I’m keeping both panels visible, switching users (admin and normal user) around and do cancel then flip filters and sort to see if reservation state leaks. What invariants should I check to confirm whether any stale state is persisting and how can I avoid false alarms?

Nice — you’re already exercising a rich interaction surface. Below are compact, testable invariants to watch for (what must always be true) plus practical ways to avoid mistaking normal behavior for a “stale state” bug. I’ll also throw in a few unusual “what‑ifs” to broaden coverage.

Invariants to check (state that must hold after any action)

Panel sync: After any reservation or cancellation, the Available Classes and My Reservations panels reflect the same underlying model (remaining slots + reservation presence). The spec requires that reservations change remaining slots and both panels refresh to reflect it (FR-24, FR-31) .
Reservation ownership: My Reservations shows exactly the reservations associated with the active User ID; changing the active user must update that panel (FR-26, FR-28) .
Cancellation rules enforced: Cancel actions must be disabled or rejected when rules apply (past class, within 1 hour, not the user’s reservation) (BR-6, BR-7, BR-8) .
Status computation correctness: Class and reservation status badges (Past / Starting soon / Upcoming / Full / Available) must be computed from current client time + remaining slots, per rules (BR-9, BR-10) .
Filters/sorts don’t mutate data: Applying filters, search, or sorting changes only the view, not class data or reservations (BR-12) .
Deterministic ordering: Given the same filter+sort parameters you should get the same ordering (BR-11, BR-13; FR-19–FR-21) .
Admin separation: Admin-only controls appear only when an admin is explicitly set, and admin edits propagate to both panels (PM-3/PM-4; FR-33, FR-39) .
No negative capacity / slot mismatches: Remaining slots must never go negative and must match reservation counts (NFR-7) .
UI update latency: UI updates (reserve/cancel/sort/filter/admin edits) should finish within the UI latency requirement (1 second); if something appears “stale” beyond that, it’s suspect (NFR-4) .
Freshness after reload: Because data is in‑memory only and page refresh resets state, any state that survives a full page reload is a bug (C-2) .
How to avoid false alarms

Respect the explicit “set user” action: The active user is applied only when you press Set User (FR-2, FR-4). If you type a different ID but don’t press the button, differences are expected — don’t call them stale state .
Allow for the 1 second UI update window: Wait up to the UI update NFR before declaring stale; many actions are required to reapply sort/filter and refresh views (NFR-4; FR-19–FR-21) .
Check view vs underlying model: Because filters/search are view-only (BR-12), if a reservation “disappears” from the Available list under active filters but still appears in My Reservations, that’s a filter effect, not leakage; confirm by clearing filters (BR-12, FR-17) .
Consider time-dependence: Status labels depend on the client clock (C-3). If tests cross the “within 1 hour” boundary or you changed the local clock, semantics will change — control or mock the clock when possible (BR-9, BR-10, C-3) .
Ensure preconditions (user set / not set): Reservation/cancel buttons are disabled when no User ID is set (FR-5). If you switch users without setting the new one, behavior may be as designed .
Watch for admin overrides: Admin edits can legitimately change class status/capacity; if an admin flips Full/Cancelled, that will change availability for regular users and isn’t a leak (FR-35, FR-40) .
Multi‑tab / session confusion: The app is client‑side in‑memory only (C-1, C-2). Different tabs won’t share memory — differences across tabs are expected unless there’s an explicit sync mechanism .
Quick checklist you can mentally run while experimenting (short form)

After cancel: My Reservations no longer lists it; Available Classes increased slots by 1; status badges recalc (FR-31) .
After reserve: My Reservations gained the item; Available Classes decreased slots by 1; no double-booking allowed (FR-24, BR-3) .
After switching user role: Admin panel visibility matches role; reservations shown are only for active user (PM-1..PM-4; FR-26) .
After filter/sort flips: Clear filters and confirm underlying counts unchanged (BR-12, FR-17) .
After page reload: All data resets (C-2) — anything persistent is an issue .
Extra “what‑ifs” and odd angles to try (to expose subtle leakage)

Rapid role flip while a reservation/cancel is in-flight (click Cancel, immediately switch user) — look for wrong target user or missed slot updates.
Apply a restrictive filter so a class disappears from Available, then cancel its reservation — does My Reservations update but Available still hides it because of the filter? That’s not a leak; it’s a view interaction (BR-12) .
Admin override capacity to 0 while a regular user holds reservations — check whether remaining slots and reservation ownership stay consistent and rules still block new reservations (FR-35, BR-2) .
Change local clock by >1 hour and observe status badge transitions and cancelability (C-3, BR-9, BR-6) .
Open multiple browser tabs: because data is in-memory, divergent states across tabs are expected — observe whether the app ever pretends they’re synchronized (it shouldn’t) (C-1, C-2) .
If you want, next I can:

Produce a short, single‑page checklist (one line per invariant) you can keep on your test rig, or
Give 6 quick “smoke” scenarios (short descriptions, not step‑by‑step) that are maximally likely to reveal stale‑state leaks.
Which would help you most next?
