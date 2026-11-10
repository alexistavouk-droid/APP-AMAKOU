import pytest

from simulator.profiles import load_profile
from simulator.scenarios import SCENARIOS, make_scenario
from simulator.vesc_engine import VescEngine


def play(sid, extra=1.0, dt=0.05):
    e = VescEngine(load_profile("default")); e.running = True
    sc = make_scenario(sid); e.set_scenario(sc)
    log = []
    for _ in range(int((sc.duration + extra) / dt)):
        log.append(e.step(dt).copy())
    return e, log


def test_all_scenarios_finish():
    for cls in SCENARIOS:
        e, _ = play(cls.id)
        assert e.scenario is None, cls.name


def test_startup():
    _, log = play(1)
    assert log[-1].soc_pct > 99 and log[-1].speed_kmh == 0 and log[-1].temp_motor < 30 and log[-1].fault == 0


def test_acceleration_monotonic_start():
    _, log = play(2)
    assert max(x.speed_kmh for x in log) > 30 and max(x.i_batt for x in log) > 10
    assert log[100].erpm > log[20].erpm


def test_deceleration():
    _, log = play(3)
    assert log[1].speed_kmh > 35 and log[-1].speed_kmh < log[1].speed_kmh * 0.6


def test_low_battery():
    _, log = play(4)
    socs = [x.soc_pct for x in log]
    assert socs[0] <= 12 and min(socs) <= 3.5
    assert log[-1].v_in < log[0].v_in


def test_overheat():
    _, log = play(5)
    assert max(x.temp_motor for x in log) >= 140 and max(x.temp_fet for x in log) >= 105
    assert min(x.power_limit_pct for x in log) < 50 and max(x.fault for x in log) in (5, 6)


def test_hard_acceleration():
    _, log = play(6)
    assert max(x.i_motor for x in log) > 30 and max(x.power_w for x in log) > 800


def test_regen():
    _, log = play(7)
    assert min(x.i_batt for x in log) < -2 and log[-1].wh_regen > 0


def test_faults_sequence():
    e = VescEngine(load_profile("default")); e.running = True
    e.set_scenario(make_scenario(8))
    seen = set()
    for _ in range(int(43 / 0.05)):
        seen.add(e.step(0.05).fault)
    assert {1, 2, 4, 5, 17} <= seen and 0 in seen
    assert e.link.drop_rate == 0 and not e.overrides


def test_link_loss_scenario():
    e = VescEngine(); e.running = True
    e.set_scenario(make_scenario(9))
    states = []
    for _ in range(int(21 / 0.05)):
        e.step(0.05); states.append(e.link.link_up)
    assert states[0] and not all(states) and states[-1]
