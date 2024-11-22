from naoqi import ALProxy, ALModule
import threading

class MotionModule(ALModule):
    def __init__(self, name, nao_ip, nao_port):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.nao_ip = nao_ip
        self.nao_port = nao_port
        self.move_timer = None
        
        self.DEFAULT_MOVEMENT_ENABLED = True
        self.DEFAULT_MOVEMENT_SPEED = 0.3
        self.DEFAULT_TURN_SPEED = 0.6
        self.DEFAULT_MOVEMENT_TIMEOUT = 5.0
        self.motion_enabled = self.DEFAULT_MOVEMENT_ENABLED
        self.movement_speed = self.DEFAULT_MOVEMENT_SPEED
        self.turn_speed = self.DEFAULT_TURN_SPEED
        self.move_timeout = self.DEFAULT_MOVEMENT_TIMEOUT
        
        # Dictionary of current key press data in the format of [{u'holding': False, u'key': u'W'}, {u'holding': False, u'key': u'A'}, {u'holding': False, u'key': u'S'}, {u'holding': False, u'key': u'D'}, {u'holding': False, u'key': u'Q'}, {u'holding': False, u'key': u'E'}]
        self.KEYS = ["W", "A", "S", "D", "Q", "E"]
        self.DEFEAULT_KEYS_PRESSED = [{u'holding': False, u'key': key} for key in self.KEYS]
        self.keys_pressed = self.DEFEAULT_KEYS_PRESSED
        """
        Name 	  	                                                    Default 	Minimum 	Maximum 	Settable
        MaxVelXY 	    maximum planar velocity (meters/second)         0.35        0.1 	    0.55 	    yes
        MaxVelTheta 	maximum angular velocity (radians/second) 	    1.0 	    0.2 	    2.00 	    yes
        MaxAccXY 	    maximum planar acceleration (meters/second^2) 	0.3 	    0.1 	    0.55 	    yes
        MaxAccTheta 	maximum angular acceleration (radians/second^2) 0.75 	    0.1 	    3.00 	    yes
        MaxJerkXY 	    maximum planar jerk (meters/second^3) 	        1.0 	    0.2 	    5.00 	    yes
        MaxJerkTheta 	maximum angular jerk (radians/second^3) 	    2.0 	    0.2 	    50.00 	    yes
        """
        self.move_config = {
            "MaxVelXY": 0.35,
            "MaxVelTheta": 1.0,
            "MaxAccXY": 0.3,
            "MaxAccTheta": 0.75,
            "MaxJerkXY": 1.0,
            "MaxJerkTheta": 2.0
        }

        self.motion = ALProxy("ALMotion", self.nao_ip, self.nao_port)
        self.memory = ALProxy("ALMemory", self.nao_ip, self.nao_port)

        self.memory.subscribeToEvent("Move", name, "on_move")
        self.memory.subscribeToEvent("StopAction", name, "stop_moving")
        self.memory.subscribeToEvent("ControlMovementSpeed", name, "on_control_movement_speed")
        self.memory.subscribeToEvent("ControlTurnSpeed", name, "on_control_turn_speed")
        self.memory.subscribeToEvent("ControlMovementTimeout", name, "on_control_movement_timeout")
        self.memory.subscribeToEvent("ControlMovement", name, "on_control_movement")

    def reset_move_timer(self):
        if self.move_timer:
            self.move_timer.cancel()
        self.move_timer = threading.Timer(self.move_timeout, self.stop_moving, args=("MoveTimeout", None))
        self.move_timer.start()

    def on_control_movement_speed(self, _, value):
        self.movement_speed = value
        print("Movement speed set to: {}".format(self.movement_speed))

    def on_move(self, _, key_press_data):
        if not self.motion_enabled:
            print("Movement is disabled, ignoring move event")
            return
        # key_press_data = ['A', False], for example, only one key received at a time
        print("Received move event with value: {}".format(key_press_data))
        self.reset_move_timer()
        x, y, theta = 0.0, 0.0, 0.0
        
        # Update keys_pressed with the new key press data
        key, holding = key_press_data
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
                elif key == "D":
                    y += self.movement_speed
                elif key == "A":
                    y -= self.movement_speed
                elif key == "E":
                    theta += self.turn_speed
                elif key == "Q":
                    theta -= self.turn_speed
                print("Key {} is being held. Updated movement values to x: {}, y: {}, theta: {}".format(key, x, y, theta))

        self.motion.move(x, y, theta, self.move_config)
        print("Moving with x: {}, y: {}, theta: {}".format(x, y, theta))

    def stop_moving(self, _, value):
        self.motion.stopMove()
        print("Stopped moving")
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