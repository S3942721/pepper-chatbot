from naoqi import ALProxy, ALModule
import threading

class MotionModule(ALModule):
    def __init__(self, name, nao_ip, nao_port):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.nao_ip = nao_ip
        self.nao_port = nao_port
        self.move_timer = None
        self.head_movement_thread = None
        self.head_movement_stop_event = threading.Event()
        
        self.MIN_HEAD_SPEED = 0.01
        self.DEFAULT_MOVEMENT_ENABLED = True
        self.DEFAULT_MOVEMENT_SPEED = 0.3
        self.DEFAULT_TURN_SPEED = 0.6
        self.DEFAULT_HEAD_SPEED = 0.2
        self.DEFAULT_MOVEMENT_TIMEOUT = 5.0
        self.motion_enabled = self.DEFAULT_MOVEMENT_ENABLED
        self.movement_speed = self.DEFAULT_MOVEMENT_SPEED
        self.turn_speed = self.DEFAULT_TURN_SPEED
        self.head_speed = self.DEFAULT_HEAD_SPEED
        self.move_timeout = self.DEFAULT_MOVEMENT_TIMEOUT
        
        self.KEYS = ["W", "A", "S", "D", "Q", "E", "ARROWUP", "ARROWDOWN", "ARROWLEFT", "ARROWRIGHT"]
        self.DEFEAULT_KEYS_PRESSED = [{u'holding': False, u'key': key} for key in self.KEYS]
        self.keys_pressed = self.DEFEAULT_KEYS_PRESSED

        self.move_config = {
            "MaxVelXY": 0.55,
            "MaxVelTheta": 2.0,
            "MaxAccXY": 0.55,
            "MaxAccTheta": 3.0,
            "MaxJerkXY": 5.0,
            "MaxJerkTheta": 50.0
        }

        self.motion = ALProxy("ALMotion", self.nao_ip, self.nao_port)
        self.memory = ALProxy("ALMemory", self.nao_ip, self.nao_port)

        self.memory.subscribeToEvent("Move", name, "on_move")
        self.memory.subscribeToEvent("ContinuousMove", name, "on_move")
        self.memory.subscribeToEvent("StopAction", name, "stop_moving")
        self.memory.subscribeToEvent("ControlMovementSpeed", name, "on_control_movement_speed")
        self.memory.subscribeToEvent("ControlTurnSpeed", name, "on_control_turn_speed")
        self.memory.subscribeToEvent("ControlMovementTimeout", name, "on_control_movement_timeout")
        self.memory.subscribeToEvent("ControlMovement", name, "on_control_movement")
        self.memory.subscribeToEvent("ControlEngagement", name, "on_control_engagement")
        self.memory.subscribeToEvent("ControlAwareness", name, "on_control_awareness")
        self.memory.subscribeToEvent("ControlContextMovement", name, "on_control_context_movement")
        self.memory.subscribeToEvent("ControlIdlePosition", name, "on_control_idle_position")
        self.memory.subscribeToEvent("ControlCollisionAvoidance", name, "on_control_collision_avoidance")
        self.memory.subscribeToEvent("LockHead", name, "lock_head")

        self.current_engagement = True
        self.current_awareness = True
        self.current_context_movement = False
        self.previous_engagement = self.current_engagement
        self.previous_awareness = self.current_awareness
        self.previous_context_movement = self.current_context_movement

    def reset_move_timer(self):
        if self.move_timer is not None:
            self.move_timer.cancel()
        self.move_timer = threading.Timer(self.move_timeout, self.stop_moving, args=("MoveTimeout", None))
        self.move_timer.start()

    def on_control_movement_speed(self, _, value):
        self.movement_speed = value
        print("Movement speed set to: {}".format(self.movement_speed))

    def on_move(self, name, move_data):
        print("MOVE FROM: ", name)
        if not self.motion_enabled:
            print("Movement is disabled, ignoring move event")
            return
        print("Received move event with value: {}".format(move_data))
        self.reset_move_timer()

        if name == "ContinuousMove":
            controller_x, controller_y, controller_hx, controller_hy = move_data
            x, y = -controller_y, -controller_x
            x_vel = self.movement_speed * x
            y_vel = self.movement_speed * y
            theta = 0.0
            for i, key in enumerate(self.KEYS):
                if self.keys_pressed[int(i)]["holding"]:
                    if key == "Q":
                        theta = self.turn_speed
                    elif key == "E":
                        theta = -self.turn_speed

            self.previous_engagement = self.current_engagement
            self.previous_awareness = self.current_awareness
            self.previous_context_movement = self.current_context_movement
            self.memory.raiseEvent("ControlEngagement", False)
            self.memory.raiseEvent("ControlAwareness", False)
            self.memory.raiseEvent("ControlContextMovement", False)
            self.motion.move(x_vel, y_vel, theta, self.move_config)
            print("Moving continuously with x: {}, y: {}".format(x, y))

            # Head movement
            head_pitch = -controller_hy * self.head_speed
            head_yaw = -controller_hx * self.head_speed
            self.motion.changeAngles(["HeadPitch", "HeadYaw"], [head_pitch, head_yaw], self.head_speed)
            print("Moving head with pitch: {}, yaw: {}".format(head_pitch, head_yaw))
        else:
            x, y, theta = 0.0, 0.0, 0.0
            key, holding = move_data
            for key_data in self.keys_pressed:
                if key_data["key"] == key:
                    key_data["holding"] = holding
                    print("Updated key press data: {}".format(self.keys_pressed))

            for i, key in enumerate(self.KEYS):
                if self.keys_pressed[int(i)]["holding"]:
                    if key == "W":
                        x += self.movement_speed
                    elif key == "S":
                        x -= self.movement_speed
                    elif key == "A":
                        y += self.movement_speed
                    elif key == "D":
                        y -= self.movement_speed
                    elif key == "Q":
                        theta += self.turn_speed
                    elif key == "E":
                        theta -= self.turn_speed
                    print("Key {} is being held. Updated movement values to x: {}, y: {}, theta: {}".format(key, x, y, theta))

            if x == 0.0 and y == 0.0 and theta == 0.0:
                self.stop_moving(None, "MoveTimeout")
            else:
                self.previous_engagement = self.current_engagement
                self.previous_awareness = self.current_awareness
                self.previous_context_movement = self.current_context_movement
                self.memory.raiseEvent("ControlEngagement", False)
                self.memory.raiseEvent("ControlAwareness", False)
                self.memory.raiseEvent("ControlContextMovement", False)
                self.motion.move(x, y, theta, self.move_config)
                print("Moving with x: {}, y: {}, theta: {}".format(x, y, theta))

            if any(key_data["holding"] for key_data in self.keys_pressed if key_data["key"] in ["ARROWUP", "ARROWDOWN", "ARROWLEFT", "ARROWRIGHT"]):
                if self.head_movement_thread is None or not self.head_movement_thread.is_alive():
                    self.head_movement_stop_event.clear()
                    self.head_movement_thread = threading.Thread(target=self.head_movement_loop)
                    self.head_movement_thread.start()
            # else:
            #     self.head_movement_stop_event.set()

    def head_movement_loop(self):
        # print("|||||||| Starting head movement loop ||||||||")
        current_head_speed = self.MIN_HEAD_SPEED
        ramp_up = True
        previous_head_pitch, previous_head_yaw = 0.0, 0.0
        while not self.head_movement_stop_event.is_set():
            # print("Head movement loop running")
            headPitch, headYaw = 0.0, 0.0
            for key_data in self.keys_pressed:
                if key_data["holding"]:
                    if key_data["key"] == "ARROWUP":
                        headPitch -= current_head_speed / 2
                        # print("Arrow Up")
                    elif key_data["key"] == "ARROWDOWN":
                        headPitch += current_head_speed / 2
                        # print("Arrow Down")
                    elif key_data["key"] == "ARROWLEFT":
                        headYaw += current_head_speed
                        # print("Arrow Left")
                    elif key_data["key"] == "ARROWRIGHT":
                        headYaw -= current_head_speed
                        # print("Arrow Right")
            if headPitch != 0.0 or headYaw != 0.0:
                # print("Head movement detected")
                current_head_speed = min(max(current_head_speed, self.MIN_HEAD_SPEED), self.head_speed)
                if ramp_up and current_head_speed < self.head_speed:
                    current_head_speed += 0.01
                # print("Current head speed: {}".format(current_head_speed))
                self.motion.changeAngles(["HeadPitch", "HeadYaw"], [headPitch, headYaw], current_head_speed)
                previous_head_pitch, previous_head_yaw = headPitch, headYaw
                # print("Moving head with pitch: {}, yaw: {}".format(headPitch, headYaw))
            else:
                # print("No head movement detected")
                if current_head_speed > self.MIN_HEAD_SPEED:
                    # print("Ramping down head movement")
                    current_head_speed -= 0.03
                    current_head_speed = max(current_head_speed, self.MIN_HEAD_SPEED)
                    self.motion.changeAngles(
                        ["HeadPitch", "HeadYaw"],
                        [previous_head_pitch / 2, previous_head_yaw / 2],
                        current_head_speed
                    )
                else:
                    # print("Head movement stopped")
                    self.head_movement_stop_event.set()
            self.head_movement_stop_event.wait(0.05)

    def stop_moving(self, _, value):
        self.motion.stopMove()
        print("Stopped moving")
        if value == "MoveTimeout":
            self.memory.raiseEvent("ControlEngagement", self.previous_engagement)
            self.memory.raiseEvent("ControlAwareness", self.previous_awareness)
            self.memory.raiseEvent("ControlContextMovement", self.previous_context_movement)
        if self.move_timer:
            print("No message received, stopping movement timer for safety")
            self.move_timer.cancel()
            self.move_timer = None

    def on_control_turn_speed(self, _, value):
        self.turn_speed = value
        print("Turn speed set to: {}".format(self.turn_speed))

    def on_control_movement_timeout(self, _, value):
        self.move_timeout = value
        print("Movement timeout set to: {}".format(self.move_timeout))

    def on_control_movement(self, _, value):
        self.motion_enabled = value
        if not self.motion_enabled:
            self.stop_moving(None, None)
        print("Movement enabled set to: {}".format(self.motion_enabled))

    def on_control_engagement(self, _, value):
        self.current_engagement = value

    def on_control_awareness(self, _, value):
        self.current_awareness = value

    def on_control_context_movement(self, _, value):
        self.current_context_movement = value

    def on_control_idle_position(self, _, value):
        self.motion.setIdlePostureEnabled("Body" ,bool(value))
        self.motion.setIdlePostureEnabled("Head" ,bool(value))
        self.motion.setIdlePostureEnabled("Arms" ,bool(value))
        self.motion.setIdlePostureEnabled("Legs" ,bool(value))
        
        print("Setting idle position to: {}".format(value))

    def on_control_collision_avoidance(self, _, value):
        print("Setting collision avoidance to: {}".format(value))
        if not value:
            self.motion.setTangentialSecurityDistance(0.01)
            self.motion.setOrthogonalSecurityDistance(0.01)
        else:
            self.motion.setTangentialSecurityDistance(0.1)
            self.motion.setOrthogonalSecurityDistance(0.4)

    def lock_head(self, _, value):
        if value:
            # Get the current head position
            head_pitch = self.motion.getAngles("HeadPitch", True)[0]
            head_yaw = self.motion.getAngles("HeadYaw", True)[0]
            self.head_lock_stop_event = threading.Event()
            self.head_lock_thread = threading.Thread(target=self.head_lock_loop, args=(head_pitch, head_yaw))
            self.head_lock_thread.start()
            print("Head locked at pitch: {}, yaw: {}".format(head_pitch, head_yaw))
        else:
            if hasattr(self, 'head_lock_stop_event'):
                self.head_lock_stop_event.set()
                print("Head lock released")

    def head_lock_loop(self, head_pitch, head_yaw):
        while not self.head_lock_stop_event.is_set():
            self.motion.setAngles(["HeadPitch", "HeadYaw"], [head_pitch, head_yaw], self.head_speed)
            self.head_lock_stop_event.wait(0.01)