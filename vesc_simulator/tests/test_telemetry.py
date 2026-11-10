import pytest

from simulator.battery_model import BATTERY_PRESETS, BatteryModel
from simulator.profiles import list_profiles, load_profile, save_profile
from simulator.vesc_engine import SimConfig, VescEngine


def run(eng, secs, dt=0.02):
    for _ in range(int(secs / dt)):
        eng.step(dt)
    return eng.snapshot()


def engine():
    e = VescEngine(); e.running = True
    return e


def test_erpm_is_mech_times_pole_pairs():
    e = engine(); e.set_override("rpm", 400)
    t = run(e, 1)
    assert t.rpm_mech == pytest.approx(400, rel=1e-3)
    assert t.erpm == pytest.approx(400 * e.cfg.pole_pairs, rel=1e-3)
    assert t.speed_kmh == pytest.approx(400 / 60 * 3.14159265 * e.cfg.wheel_diameter_m * 3.6, rel=1e-3)


def test_nominal_vs_measured_voltage():
    for name, (_, nom, vmax, vmin) in BATTERY_PRESETS.items():
        b = BatteryModel.preset(name)
        assert b.open_circuit_v(1.0) == pytest.approx(vmax)
        assert b.open_circuit_v(0.0) == pytest.approx(vmin)
        assert vmin < b.open_circuit_v(0.5) < vmax
        assert b.terminal_v(20.0) < b.open_circuit_v()     # chute sous charge


def test_acceleration_signs_and_energy():
    e = engine(); e.set_throttle(0.8)
    t = run(e, 8)
    assert t.speed_kmh > 10 and t.i_batt > 0 and t.i_motor > 0 and t.power_w > 0
    assert t.wh_used > 0 and t.soc_pct < 100 and t.v_in < e.cfg.max_v and t.distance_km > 0


def test_regen_negative_current():
    e = engine(); e.set_speed_state(35); e.set_throttle(-0.7)
    t = run(e, 3)
    assert t.i_batt < 0 and t.power_w < 0 and t.wh_regen > 0


def test_overrides_and_soc():
    e = engine()
    e.set_override("v_in", 49.5); e.set_override("temp_motor", 88); e.set_override("i_batt", 12)
    e.set_soc(33)
    t = run(e, 0.5)
    assert t.v_in == 49.5 and t.temp_motor == 88 and t.i_batt == 12 and 32 < t.soc_pct <= 33
    e.clear_override()
    assert run(e, 5).temp_motor < 88


def test_thermal_derating_and_overtemp_fault():
    e = engine(); e.set_throttle(0.5)
    e.set_override("temp_fet", 95)
    t = run(e, 1)
    assert t.power_limit_pct < 50 and t.thermal_state != "NORMAL"
    e.set_override("temp_fet", 110)
    assert run(e, 1).fault == 5


def test_time_scale_and_pause():
    a, b = engine(), engine()
    a.time_scale = 4.0
    a.set_throttle(0.5); b.set_throttle(0.5)
    run(a, 3); run(b, 3)
    assert a.t == pytest.approx(12, abs=0.1) and a.snapshot().speed_kmh > b.snapshot().speed_kmh
    b.pause(); t0 = b.t; run(b, 1)
    assert b.t == t0


def test_profiles_json(tmp_path):
    cfg = SimConfig(name="x", nominal_v=72, max_v=84, min_v=60, pole_count=20)
    save_profile(cfg, "mon_profil", tmp_path)
    assert "mon_profil" in list_profiles(tmp_path)
    assert load_profile("mon_profil", tmp_path) == cfg


def test_shipped_profiles_load():
    names = list_profiles()
    assert {"default", "trottinette_48v", "trottinette_60v", "trottinette_72v", "vehicule_84v"} <= set(names)
    for n in names:
        e = VescEngine(load_profile(n)); e.running = True
        assert run(e, 0.2).v_in > 0
