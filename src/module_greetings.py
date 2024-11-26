import threading
import time
import random
import json
from naoqi import ALProxy, ALModule
import os

class GreetingsModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.face_detected = False
        self.memory = ALProxy("ALMemory")
        self.memory.subscribeToEvent("FaceDetected", name, "on_face_detected")
        self.memory.subscribeToEvent("ControlGreetings", name, "on_control_greetings")
        self.memory.subscribeToEvent("GreetingsRequireFaceLost", name, "on_greetings_require_face_lost")
        self.memory.subscribeToEvent("LoadHTML", name, "update_profile")
        self.memory.subscribeToEvent("ChangeGreetTimeout", name, "on_speak_timeout_change")
        self.memory.subscribeToEvent("ChangeGreetFaceLostTimeout", name, "on_face_lost_timeout_change")
        self.memory.subscribeToEvent("ChangeGreetingKey", name, "on_greeting_key_change")

        self.DEFAULT_SPEAK_TIMEOUT = 3 # default seconds to wait before speaking again
        self.speak_timeout = self.DEFAULT_SPEAK_TIMEOUT # seconds to wait before speaking again
        self.DEFAULT_FACE_LOST_TIMEOUT = 1 # default seconds until face is considered lost
        self.face_lost_timeout = self.DEFAULT_FACE_LOST_TIMEOUT # seconds until face is considered lost
        self.enabled_greetings = False
        self.last_spoken_time = 0
        self.has_been_greeted = False
        self.require_face_lost = False
        self.face_lost_timer = None
        self.waiting_for_greeting = False
        self.ANNOUNCEMENTS_PATH = os.path.join(os.path.dirname(__file__), 'announcements.json')

        print("INF: GreetingsModule: Loading greetings from {}".format(self.ANNOUNCEMENTS_PATH))
        # Load the greetings from the json
        self.greetings_dictionary = {}
        with open(self.ANNOUNCEMENTS_PATH, 'r') as file:
            self.greetings_dictionary = json.load(file)
        print("INF: GreetingsModule: Loaded greetings from {}".format(self.ANNOUNCEMENTS_PATH))
        print("Loaded greetings: {}".format(self.greetings_dictionary))
        
        self.CN_GREETINGS = "City North Greetings"
        self.LTQ_GREETINGS = "LTQ Greetings"
        self.DEFAULT_GREETINGS = "Default Greetings"

        self.greetings = self.DEFAULT_GREETINGS

    def __del__(self):
        print("INF: GreetingsModule.__del__: cleaning everything")
        self.stop()
        
    def update_profile(self, event_name, value):
        if "ltq" in value.lower():
            self.greetings = self.LTQ_GREETINGS
            print("INF: GreetingsModule: Updated greetings for LTQ profile")
        elif "north" in value.lower() or "city" in value.lower():
            self.greetings = self.CN_GREETINGS
            print("INF: GreetingsModule: Updated greetings for CityNorth profile")
        else:
            self.greetings = self.DEFAULT_GREETINGS
            print("INF: GreetingsModule: Updated greetings for default profile", value)
    
    def on_control_greetings(self, event_name = None, value = False):
        self.enabled_greetings = value
        print("Received control greetings event")
        print("INF: GreetingsModule: Greetings are", "ON" if value else "OFF")

    def on_greetings_require_face_lost(self, event_name, value):
        self.require_face_lost = value
        print("INF: GreetingsModule: Greetings require face lost is", "ON" if value else "OFF")

    def on_speak_timeout_change(self, event_name, value):
        self.speak_timeout = value
        print("INF: GreetingsModule: Speak timeout changed to", value)

    def on_face_lost_timeout_change(self, event_name, value):
        self.face_lost_timeout = value
        print("INF: GreetingsModule: Face lost timeout changed to", value)

    def on_face_detected(self, event_name, value):
        if not self.enabled_greetings:
            return
        if value:
            if not self.face_detected:
                print("Face detected")
                self.handle_status_change(True)
                self.say_greeting()
            if self.face_lost_timer:
                self.face_lost_timer.cancel()
                self.face_lost_timer = None
        else:
            print("Face lost")
            if self.face_detected and not self.waiting_for_greeting and self.require_face_lost:
                self.face_lost_timer = threading.Timer(self.face_lost_timeout, self.handle_status_change, [False])
                self.face_lost_timer.start()

    def handle_status_change(self, status):
        if not self.enabled_greetings:
            return
        self.face_detected = status
        if not self.require_face_lost:
            self.face_detected = False
        if not status and not self.waiting_for_greeting:
            self.has_been_greeted = False
            print("INF: GreetingsModule: Resetting conversation")

    def say_greeting(self):
        if not self.enabled_greetings:
            return
        print("INF: GreetingsModule: Saying greeting")
        current_time = time.time()
        if current_time - self.last_spoken_time > self.speak_timeout and not (self.require_face_lost and self.has_been_greeted) and not self.waiting_for_greeting:
            self.has_been_greeted = True
            if self.greetings in self.greetings_dictionary:
                greeting = random.choice(self.greetings_dictionary[self.greetings])
            else:
                print("ERR: GreetingsModule: Invalid greetings key:", self.greetings)
                greeting = random.choice(self.greetings_dictionary[self.DEFAULT_GREETINGS])

            self.memory.raiseEvent('Say', str(greeting))
            self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "greeting_finished")
            self.waiting_for_greeting = True
            self.last_spoken_time = current_time

    def greeting_finished(self, event_name, value):
        # Consider eye contact seen after greeting to prevent immediate re-greeting if face is lost mid greeting
        self.memory.unsubscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName())
        self.waiting_for_greeting = False
        if self.require_face_lost:
            print("INF: GreetingsModule: Greeting finished")
            self.has_been_greeted = True
            self.on_face_detected(None, True)
            self.on_face_detected(None, False) # Start face lost timer in case face is not detected immediately after greeting as face lost is only triggered once on face lost

    def on_greeting_key_change(self, event_name, value):
        # Change the greetings keyword in the json file
        if value in self.greetings_dictionary:
            self.greetings = value
            print("INF: GreetingsModule: Changed greetings to {}".format(value))
        else:
            print("ERR: GreetingsModule: Invalid greetings key: {}".format(value))

    def stop(self):
        self.memory.unsubscribeToEvent("FaceDetected", self.getName())
        self.memory.unsubscribeToEvent("ControlGreetings", self.getName())
        self.memory.unsubscribeToEvent("GreetingsRequireFaceLost", self.getName())
        if self.face_lost_timer:
            self.face_lost_timer.cancel()
        print("INF: GreetingsModule: stopped!")