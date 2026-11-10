"""Chargement / sauvegarde des profils de simulation (JSON)."""
from __future__ import annotations

import json
from pathlib import Path

from simulator.vesc_engine import SimConfig

from simulator.paths import user_dir

PROFILES_DIR = user_dir("profiles")


def _dir(d) -> Path:
    return Path(d) if d else PROFILES_DIR


def list_profiles(directory=None) -> list[str]:
    return sorted(p.stem for p in _dir(directory).glob("*.json"))


def load_profile(name_or_path, directory=None) -> SimConfig:
    p = Path(name_or_path)
    if not p.suffix:
        p = _dir(directory) / f"{name_or_path}.json"
    return SimConfig.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_profile(cfg: SimConfig, name: str, directory=None) -> Path:
    d = _dir(directory)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def generate_default_profiles(directory=None) -> None:
    from simulator.battery_model import BATTERY_PRESETS
    defs = {
        "default": ("Trottinette 48 V", "48V", 15, 30, 500, 1200, 40, 25),
        "trottinette_36v": ("Trottinette 36 V", "36V", 10, 30, 350, 700, 30, 20),
        "trottinette_48v": ("Trottinette 48 V", "48V", 15, 30, 500, 1200, 40, 25),
        "trottinette_52v": ("Trottinette 52 V", "52V", 18, 30, 800, 1600, 45, 30),
        "trottinette_60v": ("Trottinette 60 V", "60V", 20, 30, 1000, 2400, 55, 40),
        "trottinette_72v": ("Trottinette 72 V", "72V", 30, 30, 2000, 4000, 70, 50),
        "vehicule_84v": ("Véhicule 84 V", "84V", 40, 28, 3000, 6000, 90, 60),
        "personnalisee": ("Configuration personnalisée", "48V", 20, 30, 750, 1500, 40, 25),
    }
    for fname, (label, preset, ah, poles, rated, maxp, imot, ibat) in defs.items():
        _, nom, vmax, vmin = BATTERY_PRESETS[preset]
        big = nom >= 72
        cfg = SimConfig(name=label, battery_preset=preset, nominal_v=nom, max_v=vmax, min_v=vmin,
                        capacity_ah=ah, pole_count=poles, rated_power_w=rated, max_power_w=maxp,
                        max_motor_current_a=imot, max_batt_current_a=ibat,
                        max_regen_current_a=imot * 0.4, mass_kg=170.0 if big else 105.0,
                        kt_nm_per_a=0.9 if big else 0.55,
                        wheel_diameter_m=0.30 if big else 0.254)
        save_profile(cfg, fname, directory)


if __name__ == "__main__":
    generate_default_profiles()
