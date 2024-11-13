import re
from naoqi import ALModule, ALProxy
import time
from tools import chat_completion
from module_expressions import BehaviourExecutor
import json
import threading
import random

class BaseSpeechReceiverModule(ALModule):
    """
    Use this object to get call back from the ALMemory of the naoqi world.
    Your callback needs to be a method with two parameter (variable name, value).
    """

    def __init__( 
            self, strModuleName, strNaoIp, port, 
            server_url, base_route, api_key, 
            model_name, save_csv=False, system_prompt='', behavior_file='behaviours_described.json'
        ):
        
        ALModule.__init__(self, strModuleName )
        self.BIND_PYTHON( self.getName(),"callback" )

        self.port = port
        self.strNaoIp = strNaoIp

        self.behaviour_file = behavior_file

        self.response_finished = True

        self.server_url = server_url
        self.base_route = base_route
        self.api_key = api_key
        self.model_name = model_name

        self.speech = ALProxy('ALAnimatedSpeech')
        self.led_service = ALProxy('ALLeds')
        self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
        self.memory.subscribeToEvent("ResetConversation", self.getName(), "clear_all")
        self.memory.subscribeToEvent("Listening", self.getName(), "handle_listening")
        self.memory.subscribeToEvent("Speaking", self.getName(), "handle_speaking")

        self.messages = []
        self.messages_to_llm = []
        self.system_prompt = system_prompt
        self.reset_message()

        self.save_csv = save_csv
        
        self.conversation_ongoing = False
        self.disable_thinking = False

        if self.save_csv:
            with open('dialogue.csv', 'w') as f:
                f.write('role,content\n')
                f.close()

        print("DEBUG: Initializing BehaviourExecutor with behaviour_file: {}".format(self.behaviour_file))
        self.executor = BehaviourExecutor(self.behaviour_file)
        
        TESTING_BEHAVIOURS = False
        
        if TESTING_BEHAVIOURS:
            index = 0
            previous_description = "<NO DESCRIPTION>"
            while index != -1:
                animation_test, index = self.executor.get_next_behaviour(index, previous_description)
                if animation_test:
                    animation_test = str(self.executor.sanitize_behaviour_requests(animation_test)[0])
                    print("DEBUG: Running test behaviour: {}".format(animation_test))
                    self.speech.say(animation_test)
                    
                    # Wait for user input for the behaviour description
                    try:
                        description = None #raw_input("Enter behaviour description (or press Enter to skip): ").strip()
                    except EOFError:
                        description = "<NO DESCRIPTION>"
                    
                    if not description:
                        description = "<NO DESCRIPTION>"
                    
                    # Log the behaviour and description
                    print("DEBUG: Behaviour: {}, Description: {}".format(animation_test, description))
                    previous_description = description
                else:
                    break


    # __init__ - end
    def __del__( self ):
        print( "INF: ReceiverModule.__del__: cleaning everything" )
        self.stop()

    def sync_messages(self):
        self.memory.raiseEvent("SyncMessages", json.dumps(self.messages))

    def clear_all(self, _, value):
        self.reset_message()
        self.conversation_ongoing = False

    def reset_message(self):
        self.messages_to_llm = [{
            "role":"system",
            "content": self.system_prompt or "You are an assistant names Pepper, your job is to answer users' questions in short."
        }]
        self.messages = []
        self.sync_messages()

    def start( self ):
        self.memory.subscribeToEvent("SpeechRecognition", self.getName(), "processRemote")
        # print( "INF: ReceiverModule: started!" )


    def stop( self ):
        print( "INF: ReceiverModule: stopping..." )
        try:
            self.memory.unsubscribe('SpeechRecognition', self.getName())
            if hasattr(self, 'stop_listening_thread'):
                self.stop_listening_thread.set()
            if hasattr(self, 'listening_thread') and self.listening_thread.is_alive():
                self.listening_thread.join()
        finally:
            print( "INF: ReceiverModule: stopped!" )

    def version( self ):
        return "1.1"
    
    def handle_speaking(self, _, speaking):
        if speaking:
            self.handle_listening(self, not speaking)
    
    def handle_listening(self, _, is_listening):
        # Runs a thread that indefinitely runs random listening behaviours until the thread is stopped
        print("DEBUG: Listening event received with value: {}".format(is_listening))
        if is_listening:
            # We are listening. We should start running "listening" behaviours
            self.listening = True
            self.stop_listening_thread = threading.Event()
            self.listening_thread = threading.Thread(target=self.run_listening_behaviours, args=(self.stop_listening_thread, self.executor, self.speech))
            self.listening_thread.start()
        else:
            # We have stopped listening. We should stop running "listening" behaviours
            if hasattr(self, 'stop_listening_thread'):
                self.stop_listening_thread.set()
            if hasattr(self, 'listening_thread') and self.listening_thread.is_alive():
                self.listening_thread.join()
            # # Set the LEDs to white
            # self.led_service.fadeRGB('AllLeds', 0xFFFFFF, 0.1)

    def run_listening_behaviours(self, stop_event, executor, speech):
        while not stop_event.is_set():
            # Set the LEDs to green
            self.led_service.fadeRGB('AllLeds', 0x00FF00, 0.1)
            # LISTENING_BEHAVIOURS = ['listening'] # FIXME: This might be doing weird things....
            # random_behaviour = random.choice(LISTENING_BEHAVIOURS)
            # listening_message = "^start({})^wait({})".format(random_behaviour, random_behaviour)
            # listening_message, _, _ = executor.sanitize_behaviour_requests(listening_message)
            # speech.say(listening_message)
            time.sleep(1)
        
        # Set the LEDs to white
        # self.led_service.fadeRGB('AllLeds', 0xFFFFFF, 0.5)

    def processRemote(self, signalName, message):
        print("DEBUG: Received message: {}".format(message))
        # While we process the message, we should stop the speech recognition
        self.memory.raiseEvent("Speaking", True)
        # Set the LEDs to white
        self.led_service.fadeRGB('AllLeds', 0xFFFFFF, 0.5)

        # Do something with the received speech recognition result
        # If pepper is triggered, only respond to messages that contain the trigger keywords
        PEPPER_TRIGGER = True
        PEPPER_NAME = "Pepper"
        PEPPER_TRIGGER_KEYWORDS = [
            "pepper", "peper", "peppa", "pepa", "papa", "pappa", "piper", "pipper", 
            "pipa", "pippa", "poppa", "pepor", "pepur", "pepr", "peppar", "peppur", 
            "peppor", "peppur", "pepur", "pepor", "pepr", "peppur", "peppor", "pepur",
            "paper", "people", "heather", "pepperoni", "feather", "baby", "puppy", "peppy",
            "poppy", "pippy", "peppermint", "debra"
        ]
        THINKING_BEHAVIOURS = ['thinking', 'think', 'thoughtful']
        THINKING_PHRASES = [
            "hmm one moment", "thinking", "let's see", "one sec", "just a sec", "let me think", 
            "hmm... one sec", "one moment", "just thinking", "give me a sec", 
            "just thinking...", "just a moment", "sorry, one sec",
            "processing that", "hmmm just a sec", "hmm let's see", "just a second", 
            "just processing", "thinking now", "thinking about that"
        ]
        
        def think_about_response(executor, speech):
            self.memory.raiseEvent("Log", "[THINK_RESP]I heard you say \""+message+"\", let me think...")
            # Set the LEDs to blue
            self.led_service.fadeRGB('AllLeds', 0x0000FF, 0.5)
            
            random_thinking_behaviour = random.choice(THINKING_BEHAVIOURS)
            random_thinking_phrase = random.choice(THINKING_PHRASES)
            thinking_message = "^start({}) {} ^stop({})".format(random_thinking_behaviour, random_thinking_phrase, random_thinking_behaviour)
            thinking_message, _, _ = executor.sanitize_behaviour_requests(thinking_message)

            speech.say(thinking_message)

        def eyes_thinking_about_response():
            # Animate the eyes to show thinking
            self.led_service.rotateEyes(0x0000FF, 1, 3)

        # the LLM will set conversation_ongoing to True if it believes the conversation is ongoing
        # When the LLM sets to false, we should reset the conversation_ongoing flag
        # New conversation will be triggered by seeing if the keywords are present and setting conversation_ongoing to True
        print("DEBUG: Received message: {}".format(message))
        
        # Replace all trigger keywords with "Pepper" in the message        
        for keyword in PEPPER_TRIGGER_KEYWORDS:
            message = re.sub(r'\b{}\b'.format(re.escape(keyword)), PEPPER_NAME, message, flags=re.IGNORECASE)

        # If we are in a pepper trigger mode, we should only respond to messages that contain "Pepper"
        if not self.conversation_ongoing and PEPPER_TRIGGER:
            if PEPPER_NAME.lower() not in message.lower():
                print("DEBUG: Message does not contain the trigger keyword 'Pepper'.")
                self.reset_message()
                self.memory.raiseEvent("Speaking", False)
                return

        print("DEBUG: Sanitised message: {}".format(message))
        
        user_msg = {'role':'user', 'content': message}
        self.messages.append(user_msg)
        self.messages_to_llm.append(user_msg)
        self.sync_messages()

        if not self.disable_thinking:
            # Set the LEDs to blue
            self.led_service.fadeRGB('AllLeds', 0x0000FF, 0.5)
            behaviour_thread = threading.Thread(target=think_about_response, args=(self.executor, self.speech))
            behaviour_thread.start()

            eyes_thread = threading.Thread(target=eyes_thinking_about_response)
            eyes_thread.start()

        start_time = time.time()
        print("DEBUG: Sending message to chatbot server")

        # Send the message to the chatbot server
        resp_text = chat_completion(
            self.server_url, 
            self.messages_to_llm, 
            route=self.base_route, 
            model_name=self.model_name, 
            api_key=self.api_key
        )
        
        print("DEBUG: Response took {} seconds.".format(time.time() - start_time))
        print("DEBUG: Received response text: {}".format(resp_text))
        
        if not self.disable_thinking:
            # Stop eyes thread
            eyes_thread.join()
            print("After eyes_thread.join()")
        
            # Forcibly stop behaviour thread
            if behaviour_thread.is_alive():
                self.stop_listening_thread.set()
                behaviour_thread.join()
        
        # Set the LEDs to white
        self.led_service.fadeRGB('AllLeds', 0xFFFFFF, 0.1)
        
        # Sanitize the response text to extract only the JSON component
        json_start = resp_text.find('{')
        json_end = resp_text.rfind('}') + 1
        if json_start != -1 and json_end != -1:
            resp_text = resp_text[json_start:json_end]
        else:
            print("DEBUG: No valid JSON found in response text.")
            self.memory.raiseEvent("Speaking", False)
            return
        
        if resp_text:
            # Decode the message JSON format, example: {'chat_response': 'Hey, how are you?', 'behaviour_request': 'hey', 'behaviour_order': 'before'}
            # Only decode the message if it is in the correct JSON format
            try:
                message_dict = eval(resp_text.replace('true', 'True').replace('false', 'False'))
                chat_response = message_dict.get('chat_response', '')
                self.conversation_ongoing = message_dict.get('conversation_ongoing', False)
                
                if not chat_response:
                    print("DEBUG: Message does not contain 'chat_response' or told not to respond.")
                    self.memory.raiseEvent("Speaking", False)
                    return

                # If we want to respond, only respond if we have a chat_response
                elif chat_response:
                    # Sanitize the chat_response to replace behaviour requests with full paths
                    chat_response, behaviour_triggered, spoken_response = self.executor.sanitize_behaviour_requests(chat_response)
                    resp_message = chat_response
                
                else:
                    print("DEBUG: Message does not contain 'chat_response'.")
                    self.memory.raiseEvent("Speaking", False)
                    return

            except (SyntaxError, KeyError) as e:
                print("DEBUG: Failed to decode message: {}".format(e))
                self.memory.raiseEvent("Speaking", False)
                return
            
            behaviour_triggered = False
            
            # Only dispaly the message if the chatbot wants to respond
            self.memory.raiseEvent("UserMessage", message)
            
            # Clear speech recognition buffer
            self.memory.raiseEvent("ClearSpeechRecognitionBuffer", None)
 
            print("AI Inference Result:\n================================\n"+resp_message+"\n================================\n")
            self.memory.raiseEvent("PepperMessage", spoken_response)
            self.memory.raiseEvent("RunningBehaviour", True)
            self.speech.say(resp_message)
            # self.memory.raiseEvent("Speaking", False)
            if(len(self.messages_to_llm) > 1):
                self.messages.append({'role':'assistant','content':resp_message})
                self.messages_to_llm.append({'role':'assistant','content':resp_text})
                self.sync_messages()

            if self.save_csv:
                with open('dialogue.csv', 'a') as f:
                    f.write('user,"'+message.replace('"', '\\"')+'"\n')
                    f.write('assistant,"'+resp_message.replace('"', '\\"')+'"\n')
                    if behaviour_triggered:
                        f.write('behaviour triggered,"'+behaviour_triggered.replace('"', '\\"')+'"\n')
                    f.close()

            if not self.conversation_ongoing:
                self.memory.raiseEvent("ResetConversation", True)

            self.memory.raiseEvent("Speaking", False)
