import time
from pathlib import Path
import sys

if __package__ is None or __package__ == "":
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from ground_station.rocket_client import RocketClient
    from ground_station.flight_controller import FlightController
else:
    from .rocket_client import RocketClient
    from .flight_controller import FlightController


def main():
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "simulator_config.yaml"

    client = RocketClient(
        config_path=str(config_path),
        host="127.0.0.1",
        port=3000,
    )

    fc = FlightController(client)

    print("[MAIN] waiting for FEEDs...")
    time.sleep(1.0)

    print("[MAIN] execute mission")
    fc.full_auto_mission()

    print(f"[MAIN] mission state: {fc.state}")
    print("[MAIN] telemetry at end:")
    print(client.get_all_telem())


if __name__ == "__main__":
    main()
