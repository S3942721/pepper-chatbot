import random
import threading
from naoqi import ALProxy, ALModule
import time
import qi
from functools import partial
import math

class ExploringModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        self.FRACTION_MAX_SPEED = 0.8
        self.MAX_WALK_VEL = 0.25 # Default 0.35, Min 0.1 Max 0.55
        self.OBSTACLE_CLOSE_DISTANCE = 0.4  # distance in meters to consider an obstacle close
        self.OBSTACLE_PERSISTANCE_TIME = 3  # number of seconds to remember the recent obstacle
        self.DISTANCE_FROM_PERSON = 0.8  # distance in meters to keep from the person
        self.CLOSE_DISTANCE_FROM_PERSON = 1.5  # distance in meters to keep from the person
        self.MOVE_THRESHOLD = 0.2  # distance in meters to consider no movement
        self.THETA_THRESHOLD = 0.1  # distance in meters to consider no movement
        self.MOVE_MIN_THRESHOLD = 0.0  # distance in meters so robot can turn
        self.THETA_MIN_THRESHOLD = 0.0  # angle in radians at min so robot can turn
        self.MANUAL_COLLISION_AVOIDANCE = False  # enable manual collision avoidance
        self.NON_INTERACTIVE_TIMEOUT = 10  # number of seconds to wait with a person before starting exploration
        self.EXPLORATION_RADIUS = 500.0  # radius in meters to explore
        self.SPEAK_TIMEOUT = 10  # number of seconds to wait before saying hello again
        # self.SPEAK_TIMEOUT = self.SPEAK_TIMEOUT * 100  # number of milliseconds to wait before saying hello again
        self.FIND_ANOTHER_PERSON_TIMEOUT = 8  # number of seconds to wait before saying hello after a conversation ends
        # self.FIND_ANOTHER_PERSON_TIMEOUT = self.FIND_ANOTHER_PERSON_TIMEOUT * 100  # time to wait before saying hello after a conversation ends
        self.EYE_CONTACT_LOST_TIMEOUT = 2  # seconds
        self.FACE_TIME_TO_LIVE = 0.5  # seconds until face is considered lost 
        self.GREET = "greet"
        self.ANNOUNCEMENT = "announcement"
        
        self.SPEAK_ON_APPROACH = True # speak when approaching a person or not
        self.ON_APPROACH = self.ANNOUNCEMENT # what to do when approaching a person
        
        self.ANNOUNCEMENTS = [
                                "^start(hey) Hello, please take your seats, we are about to begin ^wait(hey)", 
                                "^start(hey) Hi, welcome to the event ^wait(hey)", 
                                "^start(hey) Hey, welcome to the event ^wait(hey)", 
                                "^start(hey) Greetings, welcome to the event ^wait(hey)",
                                "^start(hey) I hope you are all having a great time ^wait(hey)",
                                "^start(hey) I hope you liked the presentation, I sure did ^wait(hey)",
                                "^start(hey) I hope you are having a great day! ^wait(hey)",
        ]
        
        self.GREETINGS = [
                            "^start(hey) Hello ^wait(hey)", 
                            "^start(hey) Hi ^wait(hey)", 
                            "^start(hey) Hey ^wait(hey)", 
                            "^start(hey) G'Day ^wait(hey)", 
                            "^start(hey) Greetings, I'm Pepper, what's your name? ^wait(hey)",
                            "^start(hey) Hey, my name is Pepper, pleased to meet you ^wait(hey)",
        ]
        
        self.exploring = False
        self.tracking_person = False
        self.speaking = False
        self.current_person = None
        self.visible_people = []
        self.eye_contact = False
        self.eye_contact_lost_timer = None
        self.face_6d_pos = None
        self.close_obstacle_detected = False
        self.conversation_ongoing = False
        self.move_config = [["MaxVelXY", self.MAX_WALK_VEL]]
        self.spoken_to_person = False
        self.last_speak_time = 0
        self.non_interactive_timer = None
        self.waiting_for_speaking_to_finish = False
        
        # Get the services ALNavigation and ALMotion.
        self.memory = ALProxy("ALMemory")
        # self.tracker_service = ALProxy("ALTracker")
        self.motion_service = ALProxy("ALMotion")
        self.posture_service = ALProxy("ALRobotPosture")
        self.navigation_service = ALProxy("ALNavigation")

        self.posture_service.goToPosture("StandInit", self.FRACTION_MAX_SPEED)

        # Subscribe to the events
        self.memory.subscribeToEvent("ResetConversation", self.getName(), "handle_reset_conversation")
        self.memory.subscribeToEvent("EyeContact", self.getName(), "on_eye_contact_changed")
        self.memory.subscribeToEvent("ALBasicAwareness/HumanTracked", self.getName(), "on_human_tracked")
        self.memory.subscribeToEvent("ALBasicAwareness/HumanLost", self.getName(), "on_human_tracked")
        self.memory.subscribeToEvent("FaceDetected", self.getName(), "on_face_detected")
        self.memory.subscribeToEvent("Navigation/AvoidanceNavigator/ObstacleDetected", self.getName(), "obstacle_detected")
        self.memory.subscribeToEvent("PeoplePerception/VisiblePeopleList", self.getName(), "people_visible_changed")
        self.memory.subscribeToEvent("PeoplePerception/PeopleDetected", self.getName(), "on_people_detected")
        self.memory.subscribeToEvent("ConversationOngoing", self.getName(), "handle_conversation_ongoing")
        self.memory.subscribeToEvent("Speaking", self.getName(), "handle_speaking_event")

        print("INF: ExploringModule: initialized with name: {}".format(name))

    def __del__(self):
        print("INF: ExploringModule.__del__: cleaning everything")
        self.stop_exploring()

    def people_visible_changed(self, event_name, value):
        self.visible_people = value

    def handle_reset_conversation(self, _, value):
        print("INF: handle_reset_conversation called with value: {}".format(value))
        # Start exploring if a conversation is reset - look for a new conversation partner
        if value:
            self.last_speak_time = time.time()
            self.start_exploring()
            self.waiting_for_speaking_to_finish = False

    def handle_conversation_ongoing(self, event_name, value):
        print("INF: ExploringModule: conversation_ongoing called with value: {}".format(value))
        if value:
            self.conversation_ongoing = True
            self.start_tracking()
            if self.non_interactive_timer:
                self.non_interactive_timer.cancel()
                self.non_interactive_timer = None
        else:
            self.conversation_ongoing = False

    def obstacle_detected(self, event_name, value):
        # Record the distance to the obstacle
        print("INF: ExploringModule: obstacle_detected called with value: {}".format(value))
        if value:
            x, y = value[0], value[1]
            distance = math.sqrt(x**2 + y**2)
            print("INF: ExploringModule: obstacle detected at distance: {}".format(distance))
            if distance < self.OBSTACLE_CLOSE_DISTANCE:
                self.close_obstacle_detected = True
                # Start a timer to run obstacle_expired after OBSTACLE_PERSISTANCE_TIME seconds
                threading.Timer(self.OBSTACLE_PERSISTANCE_TIME, self.obstacle_expired).start_exploring()

    def obstacle_expired(self):
        self.close_obstacle_detected = False
        print("INF: ExploringModule: obstacle expired")

    def on_people_detected(self, event_name, value):
        # See if there is a person close

        try:
            person_data = value[1]

            if person_data:
                distance_to_person = min(person[1] for person in person_data)
            else:
                distance_to_person = None

            # Check if the person is close
            self.person_close = distance_to_person < self.CLOSE_DISTANCE_FROM_PERSON

            if self.person_close:
                print("INF: ExploringModule: Person is close")
                # Asess if we want to speak to the person
                if self.SPEAK_ON_APPROACH:
                    if self.ON_APPROACH == self.GREET:
                        self.speak_to_person()
                    elif self.ON_APPROACH == self.ANNOUNCEMENT:
                        self.announce_to_person()
                
                # Stop the exploration if the person is close
                self.stop_exploring()
                self.start_tracking()

        except Exception as e:
            print("ERR: ExploringModule: People Detected Failed: {}".format(e))

    def speak_to_person(self):
        # At a maximum of once every SPEAK_TIMEOUT seconds, say a random greeting from the list
        print("INF: ExploringModule: speak_to_person called")
        if self.can_talk_to():
            print("INF: ExploringModule: Speaking to person")
            print("INF: ExploringModule: Time since last spoken: {}".format(time.time() - self.last_speak_time))
            messages = ["^start(excited) Hello ^wait(excited)", "^start(excited) Hi ^wait(excited)", "^start(excited) Hey ^wait(excited)", "^start(excited) Greetings ^wait(excited)"]
            message = random.choice(messages)
            print("INF: ExploringModule: Saying: {}".format(message))
            self.memory.raiseEvent("Say", message)
            self.spoken_to_person = True
            self.last_speak_time = time.time()

    def announce_to_person(self):
        # At a maximum of once every FIND_ANOTHER_PERSON_TIMEOUT seconds, say a random announcement from the list
        print("INF: ExploringModule: announce_to_person called")
        if self.can_talk_to():
            print("INF: ExploringModule: Announcing to person")
            print("INF: ExploringModule: Time since last spoken: {}".format(time.time() - self.last_speak_time))
            self.last_speak_time = time.time()
            self.speaking = True
            message = random.choice(self.ANNOUNCEMENTS)
            print("INF: ExploringModule: Saying: {}".format(message))
            self.memory.raiseEvent("Say", message)
            self.spoken_to_person = True
            
            # Wait for the Speaking event to raise with False and then go back to exploring
            self.waiting_for_speaking_to_finish = True

    def handle_speaking_event(self, event_name, value):
        print("INF: ExploringModule: handle_speaking_event called with value: {}".format(value))
        self.speaking = value
        if not value:
            if self.waiting_for_speaking_to_finish:
                self.memory.raiseEvent("ResetConversation", True)
                self.start_exploring()
                self.waiting_for_speaking_to_finish = False
                self.last_speak_time = time.time()

    def on_face_detected(self, event_name, value):
        """
        FaceDetected =
            [
                TimeStamp,
                [ FaceInfo[N], Time_Filtered_Reco_Info ],
                CameraPose_InTorsoFrame,
                CameraPose_InRobotFrame, *** info of interest - describes the Position6D of the camera at the time the image was taken, in FRAME_ROBOT [x,y,x,wx,wy,wz] ***
                Camera_Id
            ]
        """
        # print("INF: ExploringModule: on_face_detected called with value: {}".format(value))
        if value:
            # Restart timer for time to live of the face
            self.face_lost_timer = threading.Timer(self.FACE_TIME_TO_LIVE, self.handle_face_lost)
            
            self.face_6d_pos = value[-2]
            # print("INF: ExploringModule: Face detected at position: \nx={}, \ny={}, \nz={}, \nwx={}, \nwy={}, \nwz={}".format(face_6d_pos[0], face_6d_pos[1], face_6d_pos[2], face_6d_pos[3], face_6d_pos[4], face_6d_pos[5]))
            if not self.tracking_person:
                # Get second last elemenet of the list, which is the CameraPose_InRobotFrame
                self.face_6d_pos = value[-2]
                # self.navigate_to(face_6d_pos[0], face_6d_pos[1], face_6d_pos[3])
                # Print the position of the face x, y, z and the rotation of the face wx, wy, wz
                self.start_tracking()

    def handle_face_lost(self):
        self.face_6d_pos = None
        print("INF: ExploringModule: Face lost")

    def on_human_tracked(self, event_name, tracked_person_id):
        print("INF: ExploringModule: on_human_tracked called with value: {}".format(tracked_person_id))
        if tracked_person_id != -1 and tracked_person_id is not None and tracked_person_id is not True:
            self.current_person = tracked_person_id
            self.start_tracking()
        else:
            self.current_person = None

    def on_eye_contact_changed(self, event_name, value):
        print("INF: ExploringModule: on_eye_contact_changed called with value: {}".format(value))
        if value:
            if not self.eye_contact:
                self.eye_contact = True
                # self.start_tracking()
            if self.eye_contact_lost_timer:
                self.eye_contact_lost_timer.cancel()
                self.eye_contact_lost_timer = None
            if self.non_interactive_timer:
                self.non_interactive_timer.cancel()
                self.non_interactive_timer = None
            self.non_interactive_timer = threading.Timer(self.NON_INTERACTIVE_TIMEOUT, self.handle_non_interactive_timeout)
            self.non_interactive_timer.start()
        else:
            if self.eye_contact:
                self.eye_contact_lost_timer = threading.Timer(self.EYE_CONTACT_LOST_TIMEOUT, self.handle_eye_contact_lost)
                self.eye_contact_lost_timer.start()

    def handle_non_interactive_timeout(self):
        if not self.conversation_ongoing:
            print("INF: ExploringModule: Non-interactive timeout reached, starting exploration")
            self.start_exploring()

    def handle_eye_contact_lost(self):
        self.eye_contact = False
        self.face_6d_pos = None
        if not self.conversation_ongoing:
            print("INF: ExploringModule: eye_contact lost for x seconds, starting exploration")
            self.start_exploring()

    def can_talk_to(self):
        print("INF: ExploringModule: can_talk_to called")
        can_engage = not self.spoken_to_person and not self.speaking and not self.conversation_ongoing# and self.tracking_person
        
        if self.SPEAK_ON_APPROACH:
            if self.ON_APPROACH == self.GREET:
                print("INF: ExploringModule: Check greeting person")
                can_engage = can_engage and ((time.time() - self.last_speak_time) > self.SPEAK_TIMEOUT)
            elif self.ON_APPROACH == self.ANNOUNCEMENT:
                print("INF: ExploringModule: Check announcing to person")
                print("INF: ExploringModule: Time since last spoken: {}".format((time.time() - self.last_speak_time)))
                can_engage = can_engage and ((time.time() - self.last_speak_time) > self.FIND_ANOTHER_PERSON_TIMEOUT)

        return can_engage

    def start_tracking(self):
        if self.SPEAK_ON_APPROACH and not self.can_talk_to():
            print("INF: ExploringModule: Waiting for timeout to track person")
            self.handle_face_lost()
            return
        
        try:
            self.stop_exploring()
            
            if not self.current_person or self.current_person is None:
                raise Exception("No person to track")

            # Stop the exploration if it is running

            # Add target to track.
            print("INF: ExploringModule: Tracking person with ID: {}".format(self.current_person))

            # Extract position of a person from ID in the memory PeoplePerception/Person/<ID>/PositionInRobotFrame
            try:
                person_position = self.memory.getData("PeoplePerception/Person/" + str(self.current_person) + "/PositionInRobotFrame")

            except Exception as e:
                print("ERR: ExploringModule: Failed to get target person position: {}".format(e))
                try:
                    # Try to get the position from any other people in the memory
                    people_ids = self.visible_people
                    print("INF: ExploringModule: Failed with existing person, searching IDs: {}".format(people_ids))

                    if people_ids:
                        for person_id in people_ids:
                            if person_id is not None:
                                person_position = self.memory.getData("PeoplePerception/Person/" + str(person_id) + "/PositionInRobotFrame")
                            if person_position:
                                break

                    raise Exception("No person position found")

                except Exception as e:
                    print("ERR: ExploringModule: Failed to get any person position: {}".format(e))
                    print("INF: ExploringModule: Tracking face instead of person")
                    self.track_face(self.face_6d_pos)
                    return

            # take arctan(y/x) to get the angle
            theta = math.atan2(person_position[1], person_position[0])
            
            print("INF: ExploringModule: Person position: {}".format(person_position))
            
            # Move to x cm in front of the person, along the direction of theta
            distance_in_front = self.DISTANCE_FROM_PERSON # x cm in front of the person
            target_x = person_position[0] - distance_in_front * math.cos(theta)
            target_y = person_position[1] - distance_in_front * math.sin(theta)

            self.navigate_to(target_x, target_y, theta)
            self.tracking_person = True

        except (RuntimeError, Exception) as e:
            print("ERR: ExploringModule: Failed to track person: {}".format(e))
            # Turn to the last known face position
            self.track_face(self.face_6d_pos)

    def track_face(self, face_6d_pos):
        if face_6d_pos is not None:
            # Cast a ray to the face position and generate a 1m offset in the direction of the face theta
            face_6d_pos[0] += 1.0 * math.cos(face_6d_pos[3])
            face_6d_pos[1] += 1.0 * math.sin(face_6d_pos[3])
            
            # self.navigate_to(face_6d_pos[0], face_6d_pos[1], face_6d_pos[3]) #######################################################################################################
            self.tracking_person = True
            self.person_close = False
        else:
            print("INF: ExploringModule: No face to track, exploring instead")
            self.start_exploring()

    def stop_tracking(self):
        # Stop tracker.
        self.tracking_person = False
        self.person_close = False
        self.spoken_to_person = False
        self.handle_face_lost()
        self.eye_contact = False

    def start_exploring(self):
        print("INF: ExploringModule: start called")
        
        if self.conversation_ongoing:
            print("INF: ExploringModule: conversation ongoing, not starting exploration")
            return

        if self.exploring:
            print("INF: ExploringModule: already exploring")
            return

        # Run the exploration asynchronously
        def exploration_task(self):
            radius = self.EXPLORATION_RADIUS
            print("INF: ExploringModule: exploration_task started with radius: {}".format(radius))
            self.navigation_service.explore(radius)

        def explore():
            fut = qi.async(exploration_task, self)

        self.stop_tracking()

        print("INF: ExploringModule: starting exploration")
        explore()
        print("INF: ExploringModule: started exploring!")
        self.exploring = True

    def stop_exploring(self):
        # print("INF: ExploringModule: stop called")
        self.exploring = False
        self.navigation_service.stopExploration()
        # print("INF: ExploringModule: stopped exploring!")

    def navigate_to(self, x, y, theta):
        if self.speaking:
            print("INF: ExploringModule: Waiting for speaking to finish")
            return

        # Move to the given position
        print("INF: ExploringModule: Target navigation x={}, y={}, theta={}".format(x, y, theta))
        # self.navigation_service.navigateTo(x, y)
        front_sonar = self.memory.getData("Device/SubDeviceList/Platform/Front/Sonar/Sensor/Value")
        rear_sonar = self.memory.getData("Device/SubDeviceList/Platform/Back/Sonar/Sensor/Value")
        # left_laser = self.memory.getData("Device/SubDeviceList/Platform/LaserSensor/Left/Horizontal/Seg01/X/Sensor/Value")
        # right_laser = self.memory.getData("Device/SubDeviceList/Platform/LaserSensor/Right/Horizontal/Seg01/X/Sensor/Value")
        left_ir_obstacle = bool(self.memory.getData("Device/SubDeviceList/Platform/InfraredSpot/Left/Sensor/Value"))
        right_ir_obstacle = bool(self.memory.getData("Device/SubDeviceList/Platform/InfraredSpot/Right/Sensor/Value"))
        # Clamp x and y to ensure minimal movement threshold, if the value is less than the threshold, set to 0
        if abs(x) < self.MOVE_THRESHOLD:
            x = self.MOVE_MIN_THRESHOLD if x > 0 else -self.MOVE_MIN_THRESHOLD
        if abs(y) < self.MOVE_THRESHOLD:
            y = self.MOVE_MIN_THRESHOLD if y > 0 else -self.MOVE_MIN_THRESHOLD
        if abs(theta) < self.THETA_THRESHOLD:
            theta = self.THETA_MIN_THRESHOLD if theta > 0 else -self.THETA_MIN_THRESHOLD

        if self.close_obstacle_detected:
            print("INF: ExploringModule: close obstacle detected, using navigateTo instead of moveTo")
            self.motion_service.navigateTo(x, y)
        else:
            if self.MANUAL_COLLISION_AVOIDANCE:
                # Clamp x and y based on sensor readings
                if front_sonar < self.OBSTACLE_CLOSE_DISTANCE:
                    print("INF: ExploringModule: front_sonar: {}".format(front_sonar))
                    x = min(0, x)  # Prevent moving forward
                if rear_sonar < self.OBSTACLE_CLOSE_DISTANCE:
                    print("INF: ExploringModule: rear_sonar: {}".format(rear_sonar))
                    x = max(0, x)  # Prevent moving backward
                if left_ir_obstacle:
                    print("INF: ExploringModule: left_ir_obstacle: {}".format(left_ir_obstacle))
                    y = max(0, y)  # Prevent moving left
                if right_ir_obstacle:
                    print("INF: ExploringModule: right_ir_obstacle: {}".format(right_ir_obstacle))
                    y = min(0, y)  # Prevent moving right

            if x != 0 or y != 0 or theta != 0:
                # Move to the given position
                print("INF: ExploringModule: Navigating to x={}, y={}, theta={}".format(x, y, theta))
                self.motion_service.moveTo(x, y, theta, self.move_config)
            else:
                print("INF: ExploringModule: No movement required")
