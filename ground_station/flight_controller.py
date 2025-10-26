import time
from typing import Optional
from .rocket_client import RocketClient


class FlightState:
    IDLE = "IDLE"
    TANKING_OX = "TANKING_OX"
    OX_READY = "OX_READY"
    TANKING_FUEL = "TANKING_FUEL"
    FUEL_READY = "FUEL_READY"
    HEATING = "HEATING"
    ARMED = "ARMED"
    IGNITION_SEQUENCE = "IGNITION_SEQUENCE"
    BOOST = "BOOST"
    ASCENT = "ASCENT"
    COAST = "COAST"
    APOGEE = "APOGEE"
    DESCENT = "DESCENT"
    CHUTE_DEPLOYED = "CHUTE_DEPLOYED"
    LANDED = "LANDED"
    ABORT = "ABORT"


class FlightController:
    def __init__(self, client: RocketClient):
        self.c = client
        self.state = FlightState.IDLE

        self.apogee_alt: Optional[float] = None
        self.apogee_time: Optional[float] = None
        self.landed = False

    def _telem(self, key, default=0.0) -> float:
        val = self.c.get_telem(key, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def fuel_level(self) -> float:
        return self._telem("fuel_level", 0.0)

    def oxidizer_level(self) -> float:
        return self._telem("oxidizer_level", 0.0)

    def oxidizer_pressure(self) -> float:
        return self._telem("oxidizer_pressure", 0.0)

    def altitude(self) -> float:
        return self._telem("altitude", 0.0)

    def vertical_speed(self, sample_dt=0.3) -> float:
        """
        estimate vertical velocity in m/s
        """
        h1 = self.altitude()
        t1 = time.time()
        time.sleep(sample_dt)
        h2 = self.altitude()
        t2 = time.time()
        return (h2 - h1) / max((t2 - t1), 1e-6)

    def servo_is_closed(self, servo_name: str) -> bool:
        """
        is servo (e.g. fuel_intake) in the closed position?
        """
        pos = self._telem(servo_name + "_pos", None)
        if pos is None:
            return False
        closed_target = self.c.servo_closed_pos[servo_name]
        return abs(pos - closed_target) < 5 

    # =============== OXIDIZER LOADING ===============

    def tank_oxidizer(self):
        self.state = FlightState.TANKING_OX
        print("[SEQ] oxidizer loading: opening oxidizer_intake")

        self.c.set_servo_position(
            "oxidizer_intake",
            self.c.servo_open_pos["oxidizer_intake"]
        )

        while self.oxidizer_level() < 100.0:
            time.sleep(0.2)

        print("[SEQ] Oxidizer 100%, closing oxidizer_intake")
        self.c.set_servo_position(
            "oxidizer_intake",
            self.c.servo_closed_pos["oxidizer_intake"]
        )

        print(f"[INFO] After oxidizer fill: oxidizer_pressure={self.oxidizer_pressure():.1f} bar")
        self.state = FlightState.OX_READY

    # =============== FUEL LOADING ===============

    def tank_fuel(self):
        self.state = FlightState.TANKING_FUEL
        print("[SEQ] fuel loading: opening fuel_intake")

        self.c.set_servo_position(
            "fuel_intake",
            self.c.servo_open_pos["fuel_intake"]
        )

        while self.fuel_level() < 100.0:
            time.sleep(0.2)

        print("[SEQ] fuel 100%, closing fuel_intake")
        self.c.set_servo_position(
            "fuel_intake",
            self.c.servo_closed_pos["fuel_intake"]
        )

        self.state = FlightState.FUEL_READY

    # =============== OXIDIZER HEATING ===============

    def heat_oxidizer(self):
        self.state = FlightState.HEATING
        print("[SEQ] oxidizer heating: turning on oxidizer_heater")

        self.c.relay_open("oxidizer_heater")

        # wait until pressure reaches 55-65 bar
        while True:
            p = self.oxidizer_pressure()
            print(f"[HEAT] pressure={p:.1f} bar")

            if 55.0 <= p <= 65.0:
                print("[HEAT] Ignition window reached (55-65 bar)")
                break

            if p >= 90.0:
                print("[ABORT] pressure >=90 bar, tank explosion -> ABORT")
                self.state = FlightState.ABORT
                break

            time.sleep(0.2)

        print("[SEQ] turning off oxidizer heater")
        self.c.relay_close("oxidizer_heater")

        if self.state != FlightState.ABORT:
            self.state = FlightState.ARMED
            print("[SEQ] Rocket ARMED")

    # =============== IGNITION ===============

    def ignition_sequence(self):
        """
        - intakes must be closed,
        - oxidizer pressure 40-65 bar at ignition:
            <40 -> no ignition
            >65 -> explosion
        - fuel_main and oxidizer_main must open within <1s
        - igniter must be enabled <1s after opening main valves, and not before them
        - intakes must not be open at ignition
        """

        if self.state == FlightState.ABORT:
            return

        self.state = FlightState.IGNITION_SEQUENCE
        print("[IGN] Ignition sequence start")

        if (not self.servo_is_closed("fuel_intake")
                or not self.servo_is_closed("oxidizer_intake")):
            print("[ABORT] Intakes are not closed at ignition!")
            self.state = FlightState.ABORT
            return

        p = self.oxidizer_pressure()
        print(f"[IGN] oxidizer pressure = {p:.1f} bar")

        if p < 40.0:
            print("[IGN] pressure too low (<40 bar), engine will not ignite -> ABORT")
            self.state = FlightState.ABORT
            return

        if p > 65.0:
            print("[IGN] pressure too high (>65 bar), engine explosion -> ABORT")
            self.state = FlightState.ABORT
            return

        # open main valves for fuel/oxidizer quickly one after another
        print("[IGN] Opening fuel_main")
        self.c.set_servo_position(
            "fuel_main",
            self.c.servo_open_pos["fuel_main"]
        )

        time.sleep(0.2)

        print("[IGN] opening oxidizer_main")
        self.c.set_servo_position(
            "oxidizer_main",
            self.c.servo_open_pos["oxidizer_main"]
        )

        time.sleep(0.2)

        print("[IGN] enabling igniter")
        self.c.relay_open("igniter")

        self.state = FlightState.BOOST
        print("[IGN] engine ignited, BOOST!")

    # =============== ASCENT AND APOGEE ===============

    def climb_and_detect_apogee(self):
        """
        PHASE 1: wait until altitude actually starts increasing
        PHASE 2: monitor altitude every 0.5 s,
        when it starts going down -> apogee reached
        """

        if self.state == FlightState.ABORT:
            return

        self.state = FlightState.ASCENT
        print("[FLIGHT] ascent... waiting for the rocket to actually gain altitude")

        start_alt = self.altitude()

        while True:
            time.sleep(0.5)
            alt_now = self.altitude()
            print(f"[FLIGHT] alt={alt_now:.1f} m (arming apogee logic)")
            if alt_now - start_alt > 1.0:
                break

        last_alt = self.altitude()
        while True:
            time.sleep(0.5)
            alt_now = self.altitude()
            print(f"[FLIGHT] alt={alt_now:.1f} m (tracking climb)")

            if alt_now < last_alt:
                self.apogee_alt = last_alt
                self.apogee_time = time.time()
                self.state = FlightState.APOGEE
                print(f"[FLIGHT] APOGEE! alt_max={last_alt:.1f} m")
                break

            last_alt = alt_now

    # =============== DESCENT AND CHUTE ===============

    def descent_and_chute(self):
        """
        - parachute must be deployed <=10s after apogee,
        - mustn't be deployed at speed >30 m/s,
        - try not to deploy it very high at the top of the flight;
          wait until we've dropped a bit (<200 m) for realism,
        - if +/- 9s pass after apogee and we still haven't deployed,
          deploy anyway as a failsafe regardless of altitude,
        - if apogee was very low (<5 m), just consider it landed
        """

        if self.state == FlightState.ABORT:
            return

        if (self.apogee_alt or 0.0) < 5.0:
            print("[DESCENT] apogee very low (<5 m), skipping chute logic")
            self.state = FlightState.LANDED
            self.landed = True
            print("[LANDING] landing complete (low flight)")
            return

        self.state = FlightState.DESCENT
        print("[DESCENT] descent, preparing for parachute")

        while True:
            v_down = abs(self.vertical_speed(sample_dt=0.5))
            alt_now = self.altitude()
            t_since_apogee = time.time() - (self.apogee_time or time.time())

            print(f"[DESCENT] alt={alt_now:.1f}m |v|={v_down:.1f}m/s since_ap={t_since_apogee:.1f}s")

            low_enough = (alt_now < 200.0)   # don't deploy chute at 600m+
            safe_speed = (v_down <= 30.0)
            timeout    = (t_since_apogee > 9.0)

            if (safe_speed and low_enough) or timeout:
                print("[DESCENT] deploying parachute!")
                self.c.relay_open("parachute")
                self.state = FlightState.CHUTE_DEPLOYED
                break

            time.sleep(0.5)

        while True:
            alt1 = self.altitude()
            time.sleep(1.0)
            alt2 = self.altitude()
            if abs(alt2 - alt1) < 0.5:
                self.state = FlightState.LANDED
                self.landed = True
                print("[LANDING] landing complete")
                break

    # =============== EXECUTE MISSION ===============

    def full_auto_mission(self):
        """
        1. Fill oxidizer
        2. Fill fuel
        3. Heat oxidizer until ignition window
        4. Ignition sequence
        5. Ascent + apogee detection
        6. Descent + chute deployment + landing
        If any step -> ABORT, we stop
        """

        print("\n=== [STEP 1] TANK OXIDIZER ===")
        self.tank_oxidizer()
        if self.state == FlightState.ABORT: 
            return

        print("\n=== [STEP 2] TANK FUEL ===")
        self.tank_fuel()
        if self.state == FlightState.ABORT: 
            return

        print("\n=== [STEP 3] HEAT OXIDIZER ===")
        self.heat_oxidizer()
        if self.state == FlightState.ABORT: 
            return

        print("\n=== [STEP 4] IGNITION ===")
        self.ignition_sequence()
        if self.state == FlightState.ABORT: 
            return

        print("\n=== [STEP 5] CLIMB & APOGEE ===")
        self.climb_and_detect_apogee()
        if self.state == FlightState.ABORT: 
            return

        print("\n=== [STEP 6] DESCENT & CHUTE ===")
        self.descent_and_chute()
