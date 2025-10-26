import threading
import time
import queue
import yaml
from typing import Dict, Any

from communication_library.communication_manager import CommunicationManager, TransportType
from communication_library.tcp_transport import TcpSettings
from communication_library.frame import Frame
from communication_library import ids
from communication_library.exceptions import (
    TransportTimeoutError,
    UnregisteredCallbackError,
)


class TelemetryStore:
    """
    Simple storage of the latest known telemetry
    Updated by FEED callbacks (sensors + servo positions)
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def update(self, key: str, value: Any):
        with self._lock:
            self._data[key] = value

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def get(self, key: str, default=None) -> Any:
        with self._lock:
            return self._data.get(key, default)


class RocketClient:
    """
    high-level ground station client.

      - connects to the TCP proxy
      - sends SERVICE commands to servos/relays (open valve, fire igniter, etc.)
      - registers callbacks for FEED frames from the simulator and collects telemetry in the background
      - collects ACK/NACK in ack_queue

        client = RocketClient("simulator_config.yaml", "127.0.0.1", 3000)
        client.set_servo_position("oxidizer_intake", 0)
        client.relay_open("oxidizer_heater")
        ...
        client.get_telem("oxidizer_pressure")
    """

    def __init__(self, config_path: str = "simulator_config.yaml", host: str = "127.0.0.1", port: int = 3000):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        self.servo_map: Dict[str, int] = {}        # e.g. {"fuel_intake": 0, "oxidizer_intake": 1, ...}
        self.relay_map: Dict[str, int] = {}        # relay name -> device_id
        self.sensor_map: Dict[str, int] = {}       # sensor name -> device_id
        self.servo_open_pos: Dict[str, int] = {}   # servo_name -> "open" pos
        self.servo_closed_pos: Dict[str, int] = {} # servo_name -> "closed" pos

        for name, servo_cfg in cfg["devices"]["servo"].items():
            self.servo_map[name] = servo_cfg["device_id"]
            self.servo_open_pos[name] = servo_cfg["open_pos"]
            self.servo_closed_pos[name] = servo_cfg["closed_pos"]

        for name, relay_cfg in cfg["devices"]["relay"].items():
            self.relay_map[name] = relay_cfg["device_id"]

        for name, sensor_cfg in cfg["devices"]["sensor"].items():
            self.sensor_map[name] = sensor_cfg["device_id"]

        self.cm = CommunicationManager()
        self.cm.change_transport_type(TransportType.TCP)
        self.cm.connect(TcpSettings(host, port))

        self.telemetry = TelemetryStore()

        # queue for frames such as ACK/NACK
        self.ack_queue: "queue.Queue[Frame]" = queue.Queue()

        self._stop_flag = False

        self._register_feed_callbacks()

        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    # ============   HARDWARE COMMANDS   ============

    def set_servo_position(self, servo_name: str, position: int):
        """
        set servo position
        """
        device_id = self.servo_map[servo_name]

        frame = Frame(
            destination=ids.BoardID.ROCKET,
            priority=ids.PriorityID.LOW,
            action=ids.ActionID.SERVICE,
            source=ids.BoardID.SOFTWARE,
            device_type=ids.DeviceID.SERVO,
            device_id=device_id,
            data_type=ids.DataTypeID.INT16,
            operation=ids.OperationID.SERVO.value.POSITION,
            payload=(int(position),),
        )

        self.cm.push(frame)
        self.cm.send()

    def relay_open(self, relay_name: str):
        """
        turn relay on
        """
        device_id = self.relay_map[relay_name]

        frame = Frame(
            destination=ids.BoardID.ROCKET,
            priority=ids.PriorityID.LOW,
            action=ids.ActionID.SERVICE,
            source=ids.BoardID.SOFTWARE,
            device_type=ids.DeviceID.RELAY,
            device_id=device_id,
            data_type=ids.DataTypeID.FLOAT,
            operation=ids.OperationID.RELAY.value.OPEN,
            payload=(),
        )

        self.cm.push(frame)
        self.cm.send()

    def relay_close(self, relay_name: str):
        """
        turn relay off
        """
        device_id = self.relay_map[relay_name]

        frame = Frame(
            destination=ids.BoardID.ROCKET,
            priority=ids.PriorityID.LOW,
            action=ids.ActionID.SERVICE,
            source=ids.BoardID.SOFTWARE,
            device_type=ids.DeviceID.RELAY,
            device_id=device_id,
            data_type=ids.DataTypeID.FLOAT,
            operation=ids.OperationID.RELAY.value.CLOSE,
            payload=(),
        )

        self.cm.push(frame)
        self.cm.send()

    # ============   FEED CALLBACKS   ============

    def _register_feed_callbacks(self):
        """
        simulator sends FEED roughly once per second:
         - all sensors
         - all servo positions
        we register callbacks for each
        """

        for sensor_name, dev_id in self.sensor_map.items():
            pattern = Frame(
                destination=ids.BoardID.SOFTWARE,
                priority=ids.PriorityID.LOW,
                action=ids.ActionID.FEED,
                source=ids.BoardID.ROCKET,
                device_type=ids.DeviceID.SENSOR,
                device_id=dev_id,
                data_type=ids.DataTypeID.FLOAT,
                operation=ids.OperationID.SENSOR.value.READ,
                payload=(0.0,),
            )

            def make_cb(name):
                def _cb(frame: Frame):
                    self.telemetry.update(name, frame.payload[0])
                return _cb

            self.cm.register_callback(make_cb(sensor_name), pattern)

        # [servos] we record their position as <servo_name>_pos
        for servo_name, dev_id in self.servo_map.items():
            pattern = Frame(
                destination=ids.BoardID.SOFTWARE,
                priority=ids.PriorityID.LOW,
                action=ids.ActionID.FEED,
                source=ids.BoardID.ROCKET,
                device_type=ids.DeviceID.SERVO,
                device_id=dev_id,
                data_type=ids.DataTypeID.INT16,
                operation=ids.OperationID.SERVO.value.POSITION,
                payload=(0,),
            )

            def make_cb(name):
                def _cb(frame: Frame):
                    self.telemetry.update(name + "_pos", frame.payload[0])
                return _cb

            self.cm.register_callback(make_cb(servo_name), pattern)

    # ============   RX THREAD   ============

    def _rx_loop(self):
        """
        - cm.receive() pulls frames from the proxy/simulator
        - if the frame matches a registered FEED callback -> TelemetryStore is updated
        - if the frame doesn't match any callback, cm.receive() throws UnregisteredCallbackError and push it into ack_queue
        - if timeout then ignore
        """
        while not self._stop_flag:
            try:
                self.cm.receive()
            except TransportTimeoutError:
                pass
            except UnregisteredCallbackError as e:
                self.ack_queue.put(e.frame)
            except KeyboardInterrupt:
                break

            time.sleep(0.01)  # let CPU breathe hehe

    def stop(self):
        """
        stop flag for the RX background thread
        """
        self._stop_flag = True

    # ============   PUBLIC API   ============

    def get_telem(self, key: str, default=None):
        """
        get a telemetry value (e.g. "oxidizer_pressure")
        """
        return self.telemetry.get(key, default)

    def get_all_telem(self) -> Dict[str, Any]:
        """
        return a snapshot of all current telemetry
        """
        return self.telemetry.get_all()

    def get_servo_target_positions(self):
        """
        return a map of servo nominal open/closed positions from config
        """
        return {
            name: {
                "open": self.servo_open_pos[name],
                "closed": self.servo_closed_pos[name],
            }
            for name in self.servo_map
        }
