"""The twenty seconds this whole project exists for.

Run: python3 demo.py
"""
import sys, time
sys.path.insert(0, ".")
from hearth import Household, Ledger
from hearth.extract import extract

WEEK = 604800


def say(who, line):
    print(f"  {who:>5}: \"{line}\"")


def main():
    h = Household("home")
    dad = h.add_member("Dad", role="adult", grants=["thermostat"])
    ada = h.add_member("Ada", role="child", grants=["bedroom.ada"])
    led = Ledger(h)
    names = {m.name: mid for mid, m in h.members.items()}
    now = time.time()

    print("\nTHREE WEEKS AGO, during a cold snap")
    line = "turn it up to 24 during the cold snap"
    say("Dad", line)
    for b in extract(line, names):
        h.assert_belief(dad.id, b["domain"], b["slot"], b["value"], content=line,
                        context=b["context"], stated_at=now - 3 * WEEK)

    print("\nTHIS MORNING")
    line = "make it 20"
    say("Ada", line)
    for b in extract(line, names):
        h.assert_belief(ada.id, b["domain"], b["slot"], b["value"], content=line,
                        stated_at=now - 3600)

    print("\nTHE ASSISTANT ACTS")
    r = h.resolve("thermostat", "target")
    led.record(f"set the thermostat to {r.winner.value}", "thermostat", resolution=r)
    print(f"  Alexa: sets the thermostat to {r.winner.value}")

    print("\n  Ada: \"why did you do that?\"")
    print(f"  Alexa: {led.why()}")
    print("\n  ...the cold snap ended weeks ago. Nobody told it.")

    print("\nTHE REPAIR, spoken, no app, no settings screen")
    say("Dad", "the cold snap is over")
    ended = h.end_context("the cold snap")
    print(f"  Alexa: understood. {len(ended)} thing(s) stopped applying.")

    r2 = h.resolve("thermostat", "target")
    led.record(f"set the thermostat to {r2.winner.value}", "thermostat", resolution=r2)
    print(f"  Alexa: sets the thermostat to {r2.winner.value}")
    print(f"  Alexa: {led.why()}")

    print("\nAND THE OLD BELIEF IS NOT GONE, it is stood down and still auditable")
    for b in h.beliefs:
        mark = "live " if b.is_live() else "ended"
        print(f"  [{mark}] {b.domain}.{b.slot}={b.value:<4} "
              f"{h.name_of(b.holder):<4} {b.ended_reason or ''}")
    print()


if __name__ == "__main__":
    main()
