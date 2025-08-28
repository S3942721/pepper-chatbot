import re
from naoqi import ALModule, ALProxy
import time
from tools import chat_completion
from module_expressions import BehaviourExecutor
import json
import threading
import random
import Queue  # Python 2.7 queue module

class BaseSpeechReceiverModule(ALModule):
    """
    Use this object to get call back from the ALMemory of the naoqi world.
    Your callback needs to be a method with two parameter (variable name, value).
    """

    def __init__( 
            self, strModuleName, strNaoIp, port, 
            server_url, base_route, api_key, 
            model_name, save_csv=False, system_prompt='', behaviours_file='behaviours_described.json', sounds_file='sounds_described.json',
            expressions=None
        ):
        
        ALModule.__init__(self, strModuleName )
        self.BIND_PYTHON( self.getName(),"callback" )

        self.SAY_SIGNAL = "Say"
        self.JSON_SAY_SIGNAL = "JSONSay"

        self.port = port
        self.strNaoIp = strNaoIp
        
        self.expressions = expressions

        self.response_finished = True

        self.server_url = server_url
        self.base_route = base_route
        self.api_key = api_key
        self.model_name = model_name

        # Message queue system initialisation
        self.message_queue = Queue.Queue()
        self.queue_worker_thread = None
        self.queue_running = False
        self.queue_lock = threading.Lock()
        self.current_speech_id = None  # Track current speech for chunked responses
        self.speech_counter = 0  # Counter for unique speech IDs
        
        # Speaking state management
        self.is_currently_speaking = False
        self.speech_finished_event = threading.Event()

        self.speech = ALProxy('ALAnimatedSpeech')
        self.led_service = ALProxy('ALLeds')
        self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
        self.memory.subscribeToEvent("ResetConversation", self.getName(), "clear_all")
        self.memory.subscribeToEvent("Listening", self.getName(), "handle_listening")
        self.memory.subscribeToEvent("Speaking", self.getName(), "handle_speaking")
        self.memory.subscribeToEvent("TriggerGapFill", self.getName(), "trigger_gap_fill")
        self.memory.subscribeToEvent("StopSpeech", self.getName(), "stop_speech")
        self.memory.subscribeToEvent("StopAction", self.getName(), "stop_all")
        self.memory.subscribeToEvent("StopBehaviour", self.getName(), "stop_behaviour")
        self.memory.subscribeToEvent("StopAudio", self.getName(), "stop_audio")
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "clear_display")
        self.memory.subscribeToEvent("PepperMessage", self.getName(), "pepper_message")

        self.messages = []
        self.messages_to_llm = []
        self.system_prompt = system_prompt
        self.reset_message()

        self.save_csv = save_csv

        self.conversation_ongoing = False
        self.DISABLE_THINKING = False

        if self.save_csv:
            with open('dialogue.csv', 'w') as f:
                f.write('role,content\n')
                f.close()

        print("DEBUG: Initializing BehaviourExecutor with behaviour_file: {}".format(behaviours_file))

        TESTING_BEHAVIOURS = False

        if TESTING_BEHAVIOURS:
            index = 0
            previous_description = "<NO DESCRIPTION>"
            while index != -1:
                animation_test, index = self.expressions.get_next_behaviour(index, previous_description)
                if animation_test:
                    animation_test = str(self.expressions.sanitize_behaviour_requests(animation_test)[0])
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

        # Start the queue worker thread
        self.start_queue_worker()

    # __init__ - end
    def __del__( self ):
        print( "INF: ReceiverModule.__del__: cleaning everything" )
        self.stop()

    def sync_messages(self):
        self.memory.raiseEvent("SyncMessages", json.dumps(self.messages))

    def pepper_message(self, _, value):
        print("DEBUG: Pepper message event received with value {}".format(value))     

    def clear_display(self, _, value):
        print("DEBUG: Clear display event received")
        self.memory.raiseEvent("PepperMessage", None)
        
        # Signal that speech has finished
        self.is_currently_speaking = False
        self.speech_finished_event.set()

    def stop_speech(self, _, value):
        print("DEBUG: Stop speech event received")
        threading.Thread(target=self._stop_speech, args=(_, value)).start()

    def _stop_speech(self, _, value):
        tts = ALProxy("ALTextToSpeech")
        tts.stopAll()
        self.clear_all(_, value)

    def stop_behaviour(self, _, value):
        print("DEBUG: Stop behaviour event received")
        threading.Thread(target=self._stop_behaviour, args=(_, value)).start()

    def _stop_behaviour(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        bhv_manager = ALProxy("ALBehaviorManager")
        bhv_manager.stopAllBehaviors()

    def stop_audio(self, _, value):
        print("DEBUG: Stop audio event received")
        threading.Thread(target=self._stop_audio, args=(_, value)).start()

    def _stop_audio(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        audio_player = ALProxy("ALAudioPlayer")
        audio_player.stopAll()

    def stop_all(self, _, value):
        print("DEBUG: Stop all event received - processing any pending messages first")
        
        # Process any pending messages before clearing
        if hasattr(self, 'message_queue') and not self.message_queue.empty():
            print("DEBUG: Processing {} pending messages before stop all".format(self.message_queue.qsize()))
            # Give the queue worker a moment to process pending messages
            time.sleep(0.1)
        
        # Now clear the queue and stop speech
        self.clear_message_queue()
        self.stop_current_speech()
        
        # Original stop all functionality
        self.clear_display(_, value)
        self.stop_speech(_, value)
        self.stop_behaviour(_, value)
        self.stop_audio(_, value)

    def clear_all(self, name, value):
        """Enhanced clear all to clear message queue"""
        print("DEBUG: clear_all event received from {}".format(name))
        # Clear the message queue
        self.clear_message_queue()
        
        # Original clear all functionality
        self.reset_message()
        self.conversation_ongoing = False
        self.memory.raiseEvent("ConversationOngoing", False)
        print("DEBUG: Speaking False called in clear_all")
        self.memory.raiseEvent("Speaking", False)
        self.memory.raiseEvent("RunningBehaviour", False)

    def reset_message(self):
        self.messages_to_llm = [{
            "role":"system",
            "content": self.system_prompt or "You are an assistant names Pepper, your job is to answer users' questions in short."
        }]
        self.messages = []
        self.sync_messages()

    def start( self ):
        self.memory.subscribeToEvent("SpeechRecognition", self.getName(), "processRemote")
        self.memory.subscribeToEvent("Say", self.getName(), "processRemote")
        self.memory.subscribeToEvent("JSONSay", self.getName(), "processRemote")
        self.memory.subscribeToEvent("SayChunk", self.getName(), "processRemote")
        print( "INF: ReceiverModule: started!" )


    def stop( self ):
        """Enhanced stop to shutdown queue worker"""
        print( "INF: ReceiverModule: stopping..." )
        try:
            # Stop the queue worker
            self.stop_queue_worker()
            
            # Original stop functionality
            self.memory.unsubscribe('SpeechRecognition', self.getName())
            if hasattr(self, 'stop_listening_thread'):
                self.stop_listening_thread.set()
            if hasattr(self, 'listening_thread') and self.listening_thread.is_alive():
                self.listening_thread.join()
        finally:
            print( "INF: ReceiverModule: stopped!" )

    def trigger_gap_fill(self, _, value):
        self.disable_thinking = not value

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
            self.listening_thread = threading.Thread(target=self.run_listening_behaviours, args=(self.stop_listening_thread, self.expressions, self.speech))
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

    def start_queue_worker(self):
        """Start the message queue worker thread"""
        if not self.queue_running:
            self.queue_running = True
            self.queue_worker_thread = threading.Thread(target=self.process_message_queue)
            self.queue_worker_thread.daemon = True
            self.queue_worker_thread.start()
            print("DEBUG: Message queue worker started")

    def stop_queue_worker(self):
        """Stop the message queue worker thread"""
        self.queue_running = False
        if self.queue_worker_thread and self.queue_worker_thread.is_alive():
            # Add a special stop message to wake up the queue
            self.message_queue.put({"type": "STOP_WORKER"})
            self.queue_worker_thread.join(timeout=5)
            print("DEBUG: Message queue worker stopped")

    def process_message_queue(self):
        """Worker thread to process messages from the queue"""
        print("DEBUG: Queue worker thread started")
        
        while self.queue_running:
            try:
                # Get message from queue with timeout
                message_item = self.message_queue.get(timeout=1)
                
                # Check for stop signal
                if message_item.get("type") == "STOP_WORKER":
                    break
                
                # Process the message
                self.process_queued_message(message_item)
                
                # Mark task as done
                self.message_queue.task_done()
                
            except Queue.Empty:
                # Timeout occurred, continue loop
                continue
            except Exception as e:
                print("ERR: Queue worker error: {}".format(e))
                
        print("DEBUG: Queue worker thread ended")

    def process_queued_message(self, message_item):
        """Process a single message from the queue"""
        try:
            signal_name = message_item["signal"]
            message = message_item["message"]
            speech_id = message_item.get("speech_id")
            is_chunk = message_item.get("is_chunk", False)
            
            print("DEBUG: Processing queued message - Signal: {}, Speech ID: {}, Is Chunk: {}".format(
                signal_name, speech_id, is_chunk))
            
            # Handle chunked responses
            if is_chunk and speech_id:
                # If this is a new speech session or different from current
                if self.current_speech_id != speech_id:
                    # Stop any current speech before starting new one
                    if self.is_currently_speaking:
                        print("DEBUG: Stopping current speech for new chunk session")
                        self.stop_current_speech()
                    
                    self.current_speech_id = speech_id
                    print("DEBUG: Starting new chunked speech session: {}".format(speech_id))
                
                # For chunked responses, append to current speech or start new
                self.handle_chunked_speech(message, speech_id)
            else:
                # Regular non-chunked message processing
                if self.is_currently_speaking:
                    print("DEBUG: Stopping current speech for new message")
                    self.stop_current_speech()
                
                # Process as regular message
                self.process_message_directly(signal_name, message)
                
        except Exception as e:
            print("ERR: Error processing queued message: {}".format(e))

    def handle_chunked_speech(self, message, speech_id):
        """Handle chunked speech responses"""
        try:
            # Set speaking state immediately
            if not self.is_currently_speaking:
                self.is_currently_speaking = True
                self.memory.raiseEvent("Speaking", True)
                print("DEBUG: Speaking True set for chunked speech")
            
            # Process the message chunk
            self.process_speech_chunk(message)
            
        except Exception as e:
            print("ERR: Error handling chunked speech: {}".format(e))

    def process_speech_chunk(self, message):
        """Process a single chunk of speech"""
        try:
            # Convert the message to json if it is not already
            if message:
                message_dict = {'chat_response': message, 'conversation_ongoing': True}
                resp_text = json.dumps(message_dict)
                
                # Process the chunk
                self.process_speech_response(resp_text, is_chunk=True)
                
        except Exception as e:
            print("ERR: Error processing speech chunk: {}".format(e))

    def stop_current_speech(self):
        """Stop current speech and wait for it to finish"""
        try:
            if self.is_currently_speaking:
                # Stop all speech and behaviors
                self.memory.raiseEvent("StopAction", None)
                
                # Wait for speech to actually stop (with timeout)
                self.speech_finished_event.wait(timeout=2)
                self.speech_finished_event.clear()
                
                print("DEBUG: Current speech stopped")
        except Exception as e:
            print("ERR: Error stopping current speech: {}".format(e))

    def clear_message_queue(self):
        """Clear all pending messages from the queue"""
        with self.queue_lock:
            # Clear the queue
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
                except Queue.Empty:
                    break
            
            # Reset speech state
            self.current_speech_id = None
            print("DEBUG: Message queue cleared")

    def processRemote(self, signalName, message):
        """Add messages to queue instead of processing directly"""
        print("DEBUG: Received from: {}".format(signalName))
        print("DEBUG: Received message: {}".format(message))
        
        if message is None:
            print("DEBUG: Received message is None. Ignoring.")
            return
        
        # Check if this is a special signal that should be handled directly
        if signalName == "SayChunk":
            # Handle SayChunk as chunked response
            self.speech_counter += 1
            speech_id = "speech_{}".format(self.speech_counter)
            is_chunk = True
        else:
            # Generate unique speech ID for potential chunked responses
            self.speech_counter += 1
            speech_id = "speech_{}".format(self.speech_counter)
            # Determine if this is likely a chunked response
            is_chunk = (signalName == self.SAY_SIGNAL or signalName == self.JSON_SAY_SIGNAL)
        
        # Create message item for queue
        message_item = {
            "signal": signalName,
            "message": message,
            "speech_id": speech_id if is_chunk else None,
            "is_chunk": is_chunk,
            "timestamp": time.time()
        }
        
        # Add to queue
        try:
            self.message_queue.put(message_item, timeout=1)
            print("DEBUG: Message added to queue - Speech ID: {}, Is Chunk: {}, Queue size: {}".format(
                speech_id, is_chunk, self.message_queue.qsize()))
        except Queue.Full:
            print("ERR: Message queue is full, dropping message")

    def process_message_directly(self, signalName, message):
        """Process message directly (moved from original processRemote)"""
        print("DEBUG: Processing message directly - Signal: {}, Message: {}".format(signalName, message))
        
        # Convert the message to json if it is not already and it's a Say signal
        if message and signalName == self.SAY_SIGNAL:
            message_dict = {'chat_response': message, 'conversation_ongoing': False}
            resp_text = json.dumps(message_dict)
            # Process speech response directly
            self.process_speech_response(resp_text, is_chunk=False)
            return
        
        # Handle JSONSay signal
        if signalName == self.JSON_SAY_SIGNAL:
            self.process_speech_response(message, is_chunk=False)
            return
            
        # Handle SayChunk signal for chunked responses
        if signalName == "SayChunk":
            self.process_speech_response(message, is_chunk=True)
            return
        
        # Handle regular speech recognition from microphone
        if signalName == "SpeechRecognition":
            # Set speaking state for speech recognition processing
            self.memory.raiseEvent("Speaking", True)
            print("DEBUG: Speaking True set for speech recognition processing")
            
            # Add user message to conversation
            self.messages.append({'role':'user','content':message})
            self.messages_to_llm.append({'role':'user','content':message})
            self.sync_messages()
            
            print("User Speech Recognition Result:\n================================\n"+message+"\n================================\n")
            
            # Send to chat completion API
            try:
                resp_text = chat_completion(
                    self.server_url, 
                    self.messages_to_llm, 
                    route=self.base_route, 
                    model_name=self.model_name,
                    api_key=self.api_key
                )
                
                if resp_text:
                    self.process_speech_response(resp_text, is_chunk=False)
                else:
                    print("DEBUG: No response from chat completion API")
                    self.memory.raiseEvent("Speaking", False)
                    
            except Exception as e:
                print("ERR: Chat completion API error: {}".format(e))
                self.memory.raiseEvent("Speaking", False)

    def process_speech_response(self, resp_text, is_chunk=False):
        """Process speech response (extracted from original processRemote)"""
        try:
            # Sanitize the response text to extract only the JSON component
            json_start = resp_text.find('{')
            json_end = resp_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                resp_text = resp_text[json_start:json_end]
            else:
                print("DEBUG: No valid JSON found in response text.")
                if not is_chunk:
                    self.finish_speech_processing()
                return

            # Sanitize the response to text replace any non ascii characters with ascii equivalents
            resp_text = resp_text.encode('ascii', 'ignore').decode('ascii')

            if resp_text:
                # Decode the message JSON format
                try:
                    message_dict = eval(resp_text.replace('true', 'True').replace('false', 'False'))
                    chat_response = message_dict.get('chat_response', '')
                    self.conversation_ongoing = message_dict.get('conversation_ongoing', False)

                    if self.conversation_ongoing is True:
                        self.memory.raiseEvent("ConversationOngoing", True)

                    if not chat_response:
                        print("DEBUG: Message does not contain 'chat_response' or told not to respond.")
                        if not is_chunk:
                            self.finish_speech_processing()
                        return

                    # If we want to respond, only respond if we have a chat_response
                    elif chat_response:
                        # Sanitize the chat_response to replace behaviour requests with full paths
                        chat_response, behaviour_triggered, spoken_response = self.expressions.sanitize_request(chat_response)
                        resp_message = chat_response
                    
                    else:
                        print("DEBUG: Message does not contain 'chat_response'.")
                        if not is_chunk:
                            self.finish_speech_processing()
                        return

                except (SyntaxError, KeyError) as e:
                    print("DEBUG: Failed to decode message: {}".format(e))
                    if not is_chunk:
                        self.finish_speech_processing()
                    return
                
                # Display and process the message
                print("AI Inference Result:\n================================\n"+resp_message+"\n================================\n")
                self.memory.raiseEvent("RunningBehaviour", True)
                
                # Execute the speech
                self.speech.say(resp_message)
                
                # Update conversation state
                if len(self.messages_to_llm) > 1:
                    self.messages.append({'role':'assistant','content':resp_message})
                    self.messages_to_llm.append({'role':'assistant','content':resp_text})
                    self.sync_messages()

                # Handle conversation end for non-chunked responses
                if not is_chunk and not self.conversation_ongoing:
                    self.memory.raiseEvent("ConversationOngoing", False)
                    self.memory.raiseEvent("ResetConversation", True)

        except Exception as e:
            print("ERR: Error processing speech response: {}".format(e))
            if not is_chunk:
                self.finish_speech_processing()

    def finish_speech_processing(self):
        """Finish speech processing and reset state"""
        self.is_currently_speaking = False
        self.current_speech_id = None
        # Note: Speaking False is handled by ALAnimatedSpeech/EndOfAnimatedSpeech event