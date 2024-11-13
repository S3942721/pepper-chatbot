import threading
from naoqi import ALProxy, ALModule
import time
import qi
from functools import partial

class TrackingModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        self.FRACTION_MAX_SPEED = 0.8
        
        self.currently_tracking = False
        self.current_person = None
        self.people_ids = []

        self.memory = ALProxy("ALMemory")
        self.tracker_service = ALProxy("ALTracker")
        self.motion_service = ALProxy("ALMotion")
        self.posture_service = ALProxy("ALRobotPosture")

        # wake up motion
        self.motion_service.wakeUp()
        self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

        self.memory.subscribeToEvent("PeoplePerception/justArrived", name, "arrived")
        self.memory.subscribeToEvent("PeoplePerception/justLeft", name, "left")
        self.memory.subscribeToEvent("PeoplePerception/PeopleDetected", name, "people_detected")
        
        # Get the services ALNavigation and ALMotion.
        self.navigation_service = ALProxy("ALNavigation")
        self.motion_service = ALProxy("ALMotion")

        # Wake up robot
        self.motion_service.wakeUp()

        time.sleep(5)
        
        # Run the exploration asynchronously
        print("INF: TrackingModule: exploring environment")
        # self.exploration_promise = qi.Promise()
        # self.exploration_future = self.exploration_promise.future()
        
        def exploration_task(self):
            radius = 25.0
            self.navigation_service.explore(radius)

        def explore():
            qi.async(exploration_task, self)

        print("INF: TrackingModule: starting exploration")
        fut = explore()
        print("INF: TrackingModule: exploration started")

        time.sleep(5)
        self.navigation_service.stopExploration()
        print("INF: TrackingModule: stopping exploring environment")


    def __del__(self):
        print("INF: TrackingModule.__del__: cleaning everything")
        self.stop()

    def arrived(self, _, value):
        print("INF: TrackingModule: arrived")
        print(value)

    def left(self, _, value):
        print("INF: TrackingModule: left")
        print(value)

    def people_detected(self, _, movementInfo):
        self.people_ids = []
        for person in movementInfo[1]:
            self.people_ids.append(person[0])
            
        if self.current_person == None:
            self.current_person = self.people_ids[0]
            print("INF: TrackingModule: tracking person %s" % self.current_person)
        else:
            if self.current_person not in self.people_ids:
                if len(self.people_ids) > 0:
                    self.current_person = self.people_ids[0]
                    print("INF: TrackingModule: tracking person %s" % self.current_person)
                else:
                    print("INF: TrackingModule: lost person %s" % self.current_person)
                    self.current_person = None
            else:
                print("INF: TrackingModule: tracking person %s" % self.current_person)

        if self.current_person:
            target_name = "Person"
            self.tracker_service.registerTarget(target_name, self.current_person)

            mode = "Navigate"
            self.tracker_service.setMode(mode)

            self.tracker_service.track(target_name)

    def stop(self):
        if self.exploration_thread and self.exploration_thread.is_alive():
            self.navigation_service.stopExploration()
            self.exploration_promise.setCanceled()
            self.exploration_thread.join()
        self.memory.unsubscribeToEvent("PeoplePerception/justArrived", self.getName())
        self.memory.unsubscribeToEvent("PeoplePerception/justLeft", self.getName())
        self.memory.unsubscribeToEvent("PeoplePerception/PeopleDetected", self.getName())
        print("INF: TrackingModule: stopped!")
