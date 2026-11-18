import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze, chatlog, highlights


def fake_stream(seed=1):
    """1h de chat calme (~0,5 msg/s) avec 3 vrais moments forts + 1 raid."""
    rnd = random.Random(seed)
    ev, t0 = [], 1_000_000.0
    users = [f"u{i}" for i in range(200)]
    for s in range(3600):
        if rnd.random() < 0.5:
            ev.append({"t": t0 + s, "k": "msg", "u": rnd.choice(users[:30]), "m": "salut ça va"})
    for centre in (600, 1700, 2900):
        for s in range(centre, centre + 12):
            for _ in range(5):
                ev.append({"t": t0 + s + rnd.random(), "k": "msg", "u": rnd.choice(users), "m": rnd.choice(["KEKW", "LUL", "mdr", "OMG"])})
    ev.append({"t": t0 + 2000, "k": "event", "u": "x", "m": "raid", "w": 5})
    ev.sort(key=lambda e: e["t"])
    return t0, ev


def test_finds_the_three_peaks():
    t0, ev = fake_stream()
    moments = highlights.find_moments(ev, 10)
    peaks = sorted(round((m.peak - t0) / 100) * 100 for m in moments)
    for want in (600, 1700, 2900):
        assert any(abs(p - want) <= 100 for p in peaks), (want, peaks)
    assert len(moments) <= 5            # pas de bruit
    assert all(b.peak - a.peak >= highlights.MIN_GAP for a, b in zip(sorted(moments, key=lambda m: m.peak), sorted(moments, key=lambda m: m.peak)[1:]))


def test_quiet_stream_gives_nothing():
    rnd = random.Random(2)
    ev = [{"t": 1e6 + s, "k": "msg", "u": f"u{rnd.randint(0,20)}", "m": "ok"} for s in range(0, 3600, 2)]
    assert highlights.find_moments(ev) == []


def test_clip_window_bounds():
    m = highlights.Moment(start=1e6 + 5, end=1e6 + 15, peak=1e6 + 10, score=5)
    end, dur = analyze.clip_window(m, 1e6)
    assert 20 <= dur <= 60 and end >= dur and end - dur >= 0


def test_irc_parsing():
    line = "@bits=500;tmi-sent-ts=1700000000123 :bob!bob@bob.tmi.twitch.tv PRIVMSG #chan :LUL trop fort"
    e = chatlog.to_event(line, 0)
    assert e["u"] == "bob" and e["m"] == "LUL trop fort" and e["w"] == 5 and abs(e["t"] - 1700000000.123) < 1e-6
    sub = "@msg-id=resub;tmi-sent-ts=1700000000000 :tmi.twitch.tv USERNOTICE #chan :hi"
    assert chatlog.to_event(sub, 0)["k"] == "event"
    assert chatlog.to_event(":tmi.twitch.tv 001 justinfan1 :Welcome", 0) is None


def test_log_roundtrip(tmp_path):
    p = str(tmp_path / "l.jsonl")
    log = chatlog.ChatLog(p, "123", 1e6); log.add({"t": 2.0, "k": "msg", "u": "a", "m": "b"}); log.add({"t": 1.0, "k": "msg", "u": "a", "m": "c"}); log.close()
    h, ev = chatlog.load_log(p)
    assert h["stream_id"] == "123" and [e["t"] for e in ev] == [1.0, 2.0]
