import threading
from naoqi import ALProxy, ALModule
import time
import qi
from functools import partial

class ExploringModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        self.FRACTION_MAX_SPEED = 0.8
        self.exploring = False
        self.current_person = None
        self.people_ids = []
        self.eye_contact = False
        self.eye_contact_lost_timer = None
        self.eye_contact_lost_timeout = 5  # seconds

        # Get the services ALNavigation and ALMotion.
        self.memory = ALProxy("ALMemory")
        self.tracker_service = ALProxy("ALTracker")
        self.motion_service = ALProxy("ALMotion")
        self.posture_service = ALProxy("ALRobotPosture")
        self.navigation_service = ALProxy("ALNavigation")

        # wake up motion
        self.motion_service.wakeUp()
        self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

        # Subscribe to the events
        self.memory.subscribeToEvent("ResetConversation", self.getName(), "handle_reset_conversation")
        self.memory.subscribeToEvent("EyeContact", self.getName(), "on_eye_contact_changed")
        self.memory.subscribeToEvent("ALBasicAwareness/HumanTracked", self.getName(), "on_human_tracked")
        self.memory.subscribeToEvent("ALBasicAwareness/HumanLost", self.getName(), "on_human_tracked")

        print("INF: ExploringModule: initialized with name:", name)

    def __del__(self):
        print("INF: ExploringModule.__del__: cleaning everything")
        self.stop()

    def handle_reset_conversation(self, _, value):
        print("INF: handle_reset_conversation called with value:", value)
        # Start exploring if a conversation is reset - look for a new conversation partner
        if value:
            self.start()

    def on_human_tracked(self, event_name, tracked_person_id):
        print("INF: ExploringModule: on_human_tracked called with value:", tracked_person_id)
        if tracked_person_id != -1 and tracked_person_id is not None and tracked_person_id is not True:
            self.current_person = tracked_person_id
            # if self.exploring:
            #     self.stop()
        else:
            self.current_person = None

    def on_eye_contact_changed(self, event_name, value):
        print("INF: ExploringModule: on_eye_contact_changed called with value:", value)
        if value:
            if not self.eye_contact:
                self.eye_contact = True
                self.stop()
                self.start_tracking()
            if self.eye_contact_lost_timer:
                self.eye_contact_lost_timer.cancel()
                self.eye_contact_lost_timer = None
        else:
            if self.eye_contact:
                self.eye_contact_lost_timer = threading.Timer(self.eye_contact_lost_timeout, self.handle_eye_contact_lost)
                self.eye_contact_lost_timer.start()

    def handle_eye_contact_lost(self):
        self.eye_contact = False
        print("INF: ExploringModule: eye_contact lost for 5 seconds, starting exploration")
        self.start()

    def start_tracking(self):
        if not self.current_person:
            print("INF: ExploringModule: no person to track")
            return

        # Add target to track.
        print("INF: ExploringModule: Tracking person with ID:", self.current_person)
        targetName = "Person"
        self.tracker_service.registerTarget(targetName, self.current_person)

        # set mode
        mode = "Move"
        self.tracker_service.setMode(mode)

        # Then, start tracker.
        self.tracker_service.track(targetName)

    def stop_tracking(self):
        # Stop tracker.
        self.tracker_service.stopTracker()
        self.tracker_service.unregisterAllTargets()

    def start(self):
        print("INF: ExploringModule: start called")
        # Run the exploration asynchronously
        def exploration_task(self):
            radius = 30.0
            exploring = True
            print("INF: ExploringModule: exploration_task started with radius:", radius)
            self.navigation_service.explore(radius)

        def explore():
            fut = qi.async(exploration_task, self)

        self.stop_tracking()

        print("INF: ExploringModule: starting exploration")
        explore()
        print("INF: ExploringModule: started exploring!")
        self.exploring = True

    def stop(self):
        print("INF: ExploringModule: stop called")
        self.exploring = False
        self.navigation_service.stopExploration()
        print("INF: ExploringModule: stopped exploring!")

        # Unsubscribe from the events
        self.memory.unsubscribeToEvent("ResetConversation", self.getName())
        self.memory.unsubscribeToEvent("EyeContact", self.getName())
        print("INF: ExploringModule: unsubscribed from events")
