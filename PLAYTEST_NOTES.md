# PLAYTEST NOTES — v0.5.0 "First Five Minutes" pass

Brutally honest assessment of the new-player experience after the onboarding +
game-feel + reward + focus + economy work. Written to be useful, not flattering.

## What a new player actually sees (verified headless, frame-accurate)

1. **Opening frame.** Camera is zoomed in (1.8×, vs the 0.98× cluster default) and
   *following* MV Velawind beside Port Maren — the ship fills the view and reads
   as "you". A top-centre card says **"1. Press W to increase your throttle"**.
   A bright green marker + dashed route runs to Port Ardent (£2,000), and a faint
   focus dim drops the rest of the chart back so the objective pops.
2. **Throttle (W).** Soft click, the SPD label flashes, the ship makes way, a wake
   appears off the stern, the pulse ring beats faster. Card advances to step 2.
3. **Steer (A/D).** The hull rotates immediately (~3°/frame). Card advances to
   step 3 once you're pointed at the marker.
4. **Sail.** You follow the dashed safe-water route around Carrow. No fines, no
   grounding — the tutorial has training wheels. Card holds on "Follow the route".
5. **Dock.** Ease under 2 kn into Ardent → docking thud + rising chime, a centred
   **"CONTRACT COMPLETE  +£2,000"** banner fades in and out, the balance counts
   up, and the tutorial retires for good. The docking menu shows the **next jobs**.

Measured: the loop is legible in **~30 seconds** (throttle → steer → follow).
Bot completes the whole delivery in **~10.4 sim-hours / ~7.8 real minutes**.

## Is the first-five-minutes loop fun now? — mostly yes, with caveats

**Genuinely better:**
- A new player is **never lost**. There is exactly one accepted objective, one
  green line to follow, and a card that reacts to what they do. This is the
  single biggest win — the old build opened on a still ship with no prompt.
- The **payoff lands**. The banner + chime + count-up turn "you docked" into a
  moment. Completing a delivery now *feels* like the point of the game.
- Steering/throttle **feel responsive** — the click, SPD flash, wake and
  speed-scaled pulse close the input→feedback loop that was previously silent.
- The economy finally has **stakes**: a careless run (one grounding + a fine)
  is a *net loss* on a cheap job, and money matters against the £5k start.

## What still feels flat (the honest part)

1. **The first delivery is long.** The loop is clear in 30 s, but the *payoff*
   (the dock banner) is ~7–8 real minutes away because Maren→Ardent is 84 nm and
   the bot creeps in at 1.5 kn. A new player who doesn't discover time-compression
   (keys 3/4) may feel the middle sag. **Fix candidates:** start the tutorial job
   shorter (Maren→Saltgate is ~32 nm), or auto-nudge compression during the sail,
   or surface "press 3 for 2× speed" as a fifth tutorial hint.
2. **Clean-run margin is ~98%, not the 40–60% asked for.** I made a deliberate
   call: hitting 40–60% would require fuel to eat half of every payout, turning
   the game into a fuel-management grind that fights the "make the loop fun"
   north star. Instead, clean execution pays well and *mistakes* are the money
   sink (grounding ≈ £1,500, fines £150–500). The tension is real, but it's
   downside-driven, not margin-driven. If you want the literal target, the lever
   is a heavier fuel model — I'd advise against it.
3. **The focus dim is subtle (alpha 48).** It reads on water but barely over
   land. It nudges the eye rather than commands it. Could push to ~70 or add a
   gentle desaturation, but I kept it low after the earlier fog-overlay lesson
   (a heavy veil looked broken).
4. **Wake/pulse are tasteful but quiet.** The wake is foam dots, not a churned
   V-wake; at low zoom it's easy to miss. Fine for now; a proper tapered wake
   polygon would sell speed better.
5. **Tutorial training wheels can let a wanderer sail over land** (grounding is
   suppressed). On the guided route this never shows, but a player who ignores
   the line entirely will see the ship cross Carrow. Acceptable for a 1-run
   tutorial; worth a note.

## What I'd cut or add next (priority order)

1. **Shorten the tutorial leg** (or teach time-compression) so the first payoff
   lands inside five real minutes — the biggest remaining gap vs the brief.
2. **Second-contract handoff:** after the tutorial, auto-open the Job Board (or
   pulse it) so the "take another" step is as guided as the first.
3. **Tapered V-wake** + slightly stronger focus dim for more visible "speed" and
   "this is the objective".
4. **A small arrival cue** when entering the destination port radius ("Ease to
   under 2 kn to dock") — the dock mechanic is the one step the card can't fully
   coach mid-sail.

## Test status

- `pytest tests/ -q` → **16/16**
- `python tests/test_bot.py` → **15/15** (incl. new Scenario 15, first-five-minutes)
- `python tests/test_visual_perf.py` → draw budget under 8 ms
- First session verified headless end-to-end: steps 0→3 advance, contract pays
  £2,000, money 5000→7000, `tutorial_complete` persists.

Bottom line: the core loop is now **obvious, responsive, and rewarding** — the
three things the brief asked for. The weakest link is *pacing* (the first
delivery is longer than five minutes), not clarity. I'd fix that next.
