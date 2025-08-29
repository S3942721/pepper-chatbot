import threading
from naoqi import ALProxy, ALModule
import time
import qi
import logger

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

        logger.info("initialized with name:", name)

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
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
                    logger.warning("Could not unsubscribe from exploration events:", e)
            
            # Clean up state
            if hasattr(self, 'exploring'):
                self.exploring = False
                
        except Exception as e:
            logger.error("Error during ExploringModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def on_control_wandering(self, event_name, value):
        logger.info("on_control_wandering called with value:", value)
        if value:
            self.enabled_wandering = True
            self.start_exploring()
        else:
            self.enabled_wandering = False
            self.stop_exploring()

    def handle_speaking_event(self, event_name, value):
        logger.info("handle_speaking_event called with value:", value)
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
        # logger.info("start called")
        
        if not self.enabled_wandering:
            # logger.info("wandering is not enabled, not starting exploration")
            return

        if self.exploring:
            # logger.info("already exploring")
            return

        def exploration_task(self):
            radius = self.EXPLORATION_RADIUS
            logger.info("exploration_task started with radius:", radius)
            self.navigation_service.explore(radius)

        def explore():
            fut = getattr(qi, 'async')(exploration_task, self)

        # logger.info("starting exploration")
        explore()
        # logger.info("started exploring!")
        self.exploring = True
        
        # Change head position to look up while exploring to find more faces
        self.motion_service.setStiffnesses("Head", 1.0)
        head_pitch = -0.3
        head_yaw = 0.0
        self.motion_service.setAngles("HeadPitch", head_pitch, 0.1)
        self.motion_service.setAngles("HeadYaw", head_yaw, 0.1)
        logger.info("Head locked at pitch:", head_pitch, "yaw:", head_yaw)
        self.head_lock_stop_event = threading.Event()

        def head_control_task():
            while self.exploring and not self.head_lock_stop_event.is_set():
                # Optionally, add some dynamic behavior to head movement
                time.sleep(1.0)

        threading.Thread(target=head_control_task, daemon=True).start()

    def stop_exploring(self):
        exploring = self.exploring
        self.exploring = False
        self.navigation_service.stopExploration()

        # Send move to 0,0,0 to stop the robot
        self.motion_service.move(0.0, 0.0, 0.0)
        if exploring:
            self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

        if hasattr(self, 'head_lock_stop_event'):
            self.head_lock_stop_event.set()
            logger.info("Head lock released")

    def on_control_exploration(self, event_name, value):
        logger.info("on_control_exploration called with value:", value)
        if value:
            self.start_exploring()
        else:
            self.stop_exploring()
