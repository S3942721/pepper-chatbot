import threading
from naoqi import ALProxy, ALModule
import time
import qi

class ExploringModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        self.FRACTION_MAX_SPEED = 0.2
        self.MAX_WALK_VEL = 0.25
        self.EXPLORATION_RADIUS = 500.0
        self.START_EXPLORING_TIMEOUT = 0.01

        self.exploring = False
        self.enabled_wandering = False
        self.speaking = False
        self.non_interactive_timer = None

        self.memory = ALProxy("ALMemory")
        self.motion_service = ALProxy("ALMotion")
        self.posture_service = ALProxy("ALRobotPosture")
        self.navigation_service = ALProxy("ALNavigation")

        self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

        self.memory.subscribeToEvent("Speaking", self.getName(), "handle_speaking_event")
        self.memory.subscribeToEvent("ControlWandering", self.getName(), "on_control_wandering")
        self.memory.subscribeToEvent("ControlExploration", self.getName(), "on_control_exploration")
        self.memory.subscribeToEvent("StopAction", self.getName(), "stop_exploring")

        print("INF: ExploringModule: initialized with name: {}".format(name))

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        print("INF: ExploringModule.__del__: cleaning everything")
        
        try:
            # Stop exploration if active
            if hasattr(self, 'exploring') and self.exploring:
                try:
                    if hasattr(self, 'navigation_service'):
                        self.navigation_service.stopExploration()
                    if hasattr(self, 'motion_service'):
                        self.motion_service.move(0.0, 0.0, 0.0)
                except:
                    pass
            
            # Cancel any active timers
            if hasattr(self, 'non_interactive_timer') and self.non_interactive_timer:
                try:
                    self.non_interactive_timer.cancel()
                    self.non_interactive_timer = None
                except:
                    pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribe("Speaking", self.getName())
                    self.memory.unsubscribe("ControlWandering", self.getName())
                    self.memory.unsubscribe("ControlExploration", self.getName())
                    self.memory.unsubscribe("StopAction", self.getName())
                except Exception as e:
                    print("WARN: Could not unsubscribe from exploration events: {}".format(e))
            
            # Clean up state
            if hasattr(self, 'exploring'):
                self.exploring = False
                
        except Exception as e:
            print("ERR: Error during ExploringModule cleanup: {}".format(e))
        finally:
            print("INF: ExploringModule: cleaned up!")

    def on_control_wandering(self, event_name, value):
        print("INF: ExploringModule: on_control_wandering called with value: {}".format(value))
        if value:
            self.enabled_wandering = True
            self.start_exploring()
        else:
            self.enabled_wandering = False
            self.stop_exploring()

    def handle_speaking_event(self, event_name, value):
        print("INF: ExploringModule: handle_speaking_event called with value: {}".format(value))
        self.speaking = value
        if value:
            self.stop_exploring()
        else:
            if self.non_interactive_timer:
                self.non_interactive_timer.cancel()
                self.non_interactive_timer = None
            self.non_interactive_timer = threading.Timer(self.START_EXPLORING_TIMEOUT, self.start_exploring)
            self.non_interactive_timer.start()

    def start_exploring(self):
        # print("INF: ExploringModule: start called")
        
        if not self.enabled_wandering:
            # print("INF: ExploringModule: wandering is not enabled, not starting exploration")
            return

        if self.exploring:
            # print("INF: ExploringModule: already exploring")
            return

        def exploration_task(self):
            radius = self.EXPLORATION_RADIUS
            print("INF: ExploringModule: exploration_task started with radius: {}".format(radius))
            self.navigation_service.explore(radius)

        def explore():
            fut = qi.async(exploration_task, self)

        # print("INF: ExploringModule: starting exploration")
        explore()
        # print("INF: ExploringModule: started exploring!")
        self.exploring = True
        
        # Change head position to look up while exploring to find more faces
        self.motion_service.setStiffnesses("Head", 1.0)
        self.motion_service.setAngles("HeadPitch", -0.3, 0.1)

    def stop_exploring(self):
        exploring = self.exploring
        self.exploring = False
        self.navigation_service.stopExploration()

        # Send move to 0,0,0 to stop the robot
        self.motion_service.move(0.0, 0.0, 0.0)
        if exploring:
            self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

    def on_control_exploration(self, event_name, value):
        print("INF: ExploringModule: on_control_exploration called with value: {}".format(value))
        if value:
            self.start_exploring()
        else:
            self.stop_exploring()
