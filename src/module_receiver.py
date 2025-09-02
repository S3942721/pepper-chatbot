import re
from naoqi import ALModule, ALProxy
import time
from tools import chat_completion
from module_expressions import BehaviourExecutor
import json
import threading
import random
import Queue  # Python 2.7 queue module
import logger

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

        # Add shutdown flag
        self.shutting_down = False

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
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "finished_speaking")
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

        logger.debug("Initializing BehaviourExecutor with behaviour_file:", behaviours_file)

        TESTING_BEHAVIOURS = False

        if TESTING_BEHAVIOURS:
            index = 0
            previous_description = "<NO DESCRIPTION>"
            while index != -1:
                animation_test, index = self.expressions.get_next_behaviour(index, previous_description)
                if animation_test:
                    animation_test = str(self.expressions.sanitise_behaviour_requests(animation_test)[0])
                    logger.debug("Running test behaviour:", animation_test)
                    self.speech.say(animation_test)
                    
                    # Wait for user input for the behaviour description
                    try:
                        description = None #raw_input("Enter behaviour description (or press Enter to skip): ").strip()
                    except EOFError:
                        description = "<NO DESCRIPTION>"
                    
                    if not description:
                        description = "<NO DESCRIPTION>"
                    
                    # Log the behaviour and description
                    logger.debug("Behaviour:", animation_test, "Description:", description)
                    previous_description = description
                else:
                    break

        # Start the queue worker thread
        self.start_queue_worker()

    # __init__ - end
    def __del__( self ):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        # Set shutdown flag to prevent new message processing
        self.shutting_down = True
        
        try:
            # Stop the queue worker first
            if hasattr(self, 'queue_running'):
                self.queue_running = False
                if hasattr(self, 'queue_worker_thread') and self.queue_worker_thread and self.queue_worker_thread.is_alive():
                    try:
                        # Add stop signal to wake up the queue
                        if hasattr(self, 'message_queue'):
                            self.message_queue.put({"type": "STOP_WORKER"})
                        self.queue_worker_thread.join(timeout=3)
                    except:
                        pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribe('SpeechRecognition', self.getName())
                    self.memory.unsubscribe('Say', self.getName())
                    self.memory.unsubscribe('JSONSay', self.getName())
                    self.memory.unsubscribe('SayChunk', self.getName())
                    self.memory.unsubscribe('Speaking', self.getName())
                    self.memory.unsubscribe('StopAction', self.getName())
                    self.memory.unsubscribe('StopSpeech', self.getName())
                    self.memory.unsubscribe('StopBehaviour', self.getName())
                    self.memory.unsubscribe('StopAudio', self.getName())
                    self.memory.unsubscribe('ALAnimatedSpeech/EndOfAnimatedSpeech', self.getName())
                    self.memory.unsubscribe('PepperMessage', self.getName())
                    self.memory.unsubscribe('ResetConversation', self.getName())
                    self.memory.unsubscribe('Listening', self.getName())
                    self.memory.unsubscribe('TriggerGapFill', self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from receiver events:", e)
            
            # Stop listening thread
            if hasattr(self, 'stop_listening_thread'):
                try:
                    self.stop_listening_thread.set()
                except:
                    pass
            if hasattr(self, 'listening_thread') and self.listening_thread and self.listening_thread.is_alive():
                try:
                    self.listening_thread.join(timeout=1)
                except:
                    pass
                    
        except Exception as e:
            logger.error("Error during ReceiverModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def sync_messages(self):
        self.memory.raiseEvent("SyncMessages", json.dumps(self.messages))

    def pepper_message(self, _, value):
        logger.debug("Pepper message event received with value", value)     

    def finished_speaking(self, _, value):
        logger.debug("Clear display event received")
        self.memory.raiseEvent("PepperMessage", None)
        
        # Signal that speech has finished
        self.is_currently_speaking = False
        self.speech_finished_event.set()

        # Don't raise Speaking events directly - let speaking manager handle it
        logger.debug("Speech finished, letting speaking manager handle Speaking state")

    def stop_speech(self, _, value):
        logger.debug("Stop speech event received")
        threading.Thread(target=self._stop_speech, args=(_, value)).start()

    def _stop_speech(self, _, value):
        tts = ALProxy("ALTextToSpeech")
        tts.stopAll()
        self.clear_all(_, value)

    def stop_behaviour(self, _, value):
        logger.debug("Stop behaviour event received")
        threading.Thread(target=self._stop_behaviour, args=(_, value)).start()

    def _stop_behaviour(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        bhv_manager = ALProxy("ALBehaviorManager")
        bhv_manager.stopAllBehaviors()

    def stop_audio(self, _, value):
        logger.debug("Stop audio event received")
        threading.Thread(target=self._stop_audio, args=(_, value)).start()

    def _stop_audio(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        audio_player = ALProxy("ALAudioPlayer")
        audio_player.stopAll()

    def stop_all(self, _, value):
        """Stop current speech/behaviours but do NOT clear pending queued messages.

        StopAction is often raised before the Say event (socket shortcuts). If we clear
        the queue here we risk discarding the very Say we are about to enqueue.
        Keep behaviour stopping but preserve the queue so incoming Say/SayChunk will run.
        """
        logger.debug("Stop all event received - stopping speech and behaviours (queue preserved)")

        # Stop current speech only (allow pending queued messages to be processed)
        self.stop_current_speech()

        # Original stop all functionality (stop display/behaviours/audio)
        self.finished_speaking(_, value)
        self.stop_speech(_, value)
        self.stop_behaviour(_, value)
        self.stop_audio(_, value)

    def clear_all(self, name, value):
        """Enhanced clear all to clear message queue"""
        logger.debug("clear_all event received from", name)
        # Clear the message queue
        self.clear_message_queue()
        
        # Original clear all functionality
        self.reset_message()
        self.conversation_ongoing = False
        self.memory.raiseEvent("ConversationOngoing", False)
        
        # Stop speaking via speaking manager instead of direct Speaking event
        self.memory.raiseEvent("StopSpeaking", None)
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
        logger.info("started!")

    def stop( self ):
        """Enhanced stop to shutdown queue worker"""
        logger.info("stopping...")
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
            logger.info("stopped!")

    def trigger_gap_fill(self, _, value):
        self.disable_thinking = not value

    def handle_speaking(self, _, speaking):
        if speaking:
            self.handle_listening(self, not speaking)
    
    def handle_listening(self, _, is_listening):
        # Runs a thread that indefinitely runs random listening behaviours until the thread is stopped
        logger.debug("Listening event received with value:", is_listening)
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
            # listening_message, _, _ = executor.sanitise_behaviour_requests(listening_message)
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
            logger.debug("Message queue worker started")

    def stop_queue_worker(self):
        """Stop the message queue worker thread"""
        self.queue_running = False
        if self.queue_worker_thread and self.queue_worker_thread.is_alive():
            # Add a special stop message to wake up the queue
            self.message_queue.put({"type": "STOP_WORKER"})
            self.queue_worker_thread.join(timeout=5)
            logger.debug("Message queue worker stopped")

    def process_message_queue(self):
        """Worker thread to process messages from the queue"""
        logger.debug("Queue worker thread started")
        
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
                logger.error("Queue worker error:", e)
                
        logger.debug("Queue worker thread ended")

    def process_queued_message(self, message_item):
        """Process a single message from the queue"""
        try:
            signal_name = message_item["signal"]
            message = message_item["message"]
            speech_id = message_item.get("speech_id")
            is_chunk = message_item.get("is_chunk", False)
            
            logger.debug("Processing queued message - Signal:", signal_name, "Speech ID:", speech_id, "Is Chunk:", is_chunk)
            
            # Notify speaking manager about queue activity
            self.memory.raiseEvent("DequeueResult", {"speech_id": speech_id, "is_chunk": is_chunk})
            
            # Handle chunked responses
            if is_chunk and speech_id:
                # If this is a new speech session or different from current
                if self.current_speech_id != speech_id:
                    # Stop any current speech before starting new one
                    if self.is_currently_speaking:
                        logger.debug("Stopping current speech for new chunk session")
                        self.stop_current_speech()
                    
                    self.current_speech_id = speech_id
                    logger.debug("Starting new chunked speech session:", speech_id)
                
                # For chunked responses, append to current speech or start new
                self.handle_chunked_speech(message, speech_id)
            else:
                # Regular non-chunked message processing
                if self.is_currently_speaking:
                    logger.debug("Stopping current speech for new message")
                    self.stop_current_speech()
                
                # Process as regular message
                self.process_message_directly(signal_name, message)
            
            # Check if this was the last message in the queue
            try:
                with self.queue_lock:
                    queue_empty_after_processing = self.message_queue.empty()
                if queue_empty_after_processing and not self.is_currently_speaking:
                    logger.debug("Queue empty after processing, notifying speaking manager")
                    # Let speaking manager determine if Speaking should be False
                    # Don't directly raise Speaking False here
            except Exception:
                pass
                
        except Exception as e:
            logger.error("Error processing queued message:", e)

    def handle_chunked_speech(self, message, speech_id):
        """Handle chunked speech responses"""
        try:
            # Don't set speaking state here - it should already be True from previous chunks
            # or will be set in process_speech_response
            logger.debug("Handling chunked speech for session:", speech_id)
            
            # Process the message chunk
            self.process_speech_chunk(message)
            
        except Exception as e:
            logger.error("Error handling chunked speech:", e)

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
            logger.error("Error processing speech chunk:", e)

    def stop_current_speech(self):
        """Stop current speech without triggering global StopAction (preserve queue)."""
        try:
            if self.is_currently_speaking:
                # Stop animated speech / tts directly, avoid raising StopAction which clears queues elsewhere
                try:
                    tts = ALProxy("ALTextToSpeech")
                    tts.stopAll()
                except Exception:
                    pass
                try:
                    # ALAnimatedSpeech may also be speaking
                    self.speech.stopAll()
                except Exception:
                    pass

                # Signal running behaviour stopped
                try:
                    self.memory.raiseEvent("RunningBehaviour", False)
                except Exception:
                    pass

                # Wait for ALAnimatedSpeech end event to set the finished event (with timeout)
                self.speech_finished_event.wait(timeout=2)
                self.speech_finished_event.clear()

                # Update state
                self.is_currently_speaking = False
                logger.debug("Current speech stopped (direct stop)")
        except Exception as e:
            logger.error("Error stopping current speech:", e)

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
            logger.debug("Message queue cleared")

    def processRemote(self, signalName, message):
        """Add messages to queue instead of processing directly"""
        # Don't process new messages during shutdown
        if getattr(self, 'shutting_down', False):
            return

        logger.debug("Received from:", signalName)
        logger.debug("Received message:", message)

        if message is None:
            logger.debug("Received message is None. Ignoring.")
            return

        # Pre-sanitise speech chunks before queuing
        sanitised_message = message
        if signalName in [self.SAY_SIGNAL, self.JSON_SAY_SIGNAL, "SayChunk"]:
            try:
                # Extract JSON if needed
                if signalName == self.SAY_SIGNAL:
                    message_dict = {'chat_response': message, 'conversation_ongoing': False}
                    json_message = json.dumps(message_dict)
                else:
                    json_message = message

                # Parse JSON to get chat_response
                json_start = json_message.find('{')
                json_end = json_message.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    resp_text = json_message[json_start:json_end]
                    resp_text = resp_text.encode('ascii', 'ignore').decode('ascii')
                    
                    try:
                        message_dict = eval(resp_text.replace('true', 'True').replace('false', 'False'))
                        chat_response = message_dict.get('chat_response', '')
                        
                        if chat_response and self.expressions:
                            # Perform sanitisation early for speech chunks
                            sanitised_response, behaviour_triggered, spoken_response = self.expressions.sanitise_request(chat_response)

                            # Update the message dict with sanitised content
                            message_dict['chat_response'] = sanitised_response
                            message_dict['sanitised'] = True  # Mark as pre-sanitised
                            message_dict['spoken_response'] = spoken_response
                            message_dict['behaviour_triggered'] = behaviour_triggered
                            
                            # Convert back to JSON string
                            sanitised_message = json.dumps(message_dict)
                            logger.debug("Pre-sanitised speech chunk before queuing")
                        else:
                            sanitised_message = json_message
                    except (SyntaxError, KeyError) as e:
                        logger.debug("Failed to pre-sanitise message:", e)
                        sanitised_message = json_message
                else:
                    sanitised_message = json_message
                    
            except Exception as e:
                logger.debug("Error during pre-sanitisation:", e)
                sanitised_message = message
        
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
        
        # Create message item for queue with sanitised content
        message_item = {
            "signal": signalName,
            "message": sanitised_message,
            "speech_id": speech_id if is_chunk else None,
            "is_chunk": is_chunk,
            "timestamp": time.time()
        }
        
        # Notify speaking manager about queue activity
        if is_chunk:
            self.memory.raiseEvent("QueueSpeech", {"speech_id": speech_id, "is_chunk": is_chunk})
        
        # Add to queue
        try:
            self.message_queue.put(message_item, timeout=1)
            logger.debug("Message added to queue - Speech ID:", speech_id, "Is Chunk:", is_chunk, "Queue size:", self.message_queue.qsize())
        except Queue.Full:
            logger.error("Message queue is full, dropping message")

    def process_speech_response(self, resp_text, is_chunk=False):
        """Process speech response (extracted from original processRemote)"""
        # sanitise the response text to extract only the JSON component
        json_start = resp_text.find('{')
        json_end = resp_text.rfind('}') + 1
        if json_start != -1 and json_end != -1:
            resp_text = resp_text[json_start:json_end]
        else:
            logger.debug("No valid JSON found in response text.")
            if not is_chunk:
                self.finish_speech_processing()
            return

        try:
            # sanitise the response to text replace any non ascii characters with ascii equivalents
            resp_text = resp_text.encode('ascii', 'ignore').decode('ascii')

            if resp_text:
                # Decode the message JSON format
                try:
                    message_dict = eval(resp_text.replace('true', 'True').replace('false', 'False'))
                    chat_response = message_dict.get('chat_response', '')
                    self.conversation_ongoing = message_dict.get('conversation_ongoing', False)
                    
                    # Check if response was pre-sanitised
                    pre_sanitised = message_dict.get('sanitised', False)

                    if self.conversation_ongoing is True:
                        self.memory.raiseEvent("ConversationOngoing", True)

                    if not chat_response:
                        logger.debug("Message does not contain 'chat_response' or told not to respond.")
                        if not is_chunk:
                            self.finish_speech_processing()
                        return

                    # If we want to respond, only respond if we have a chat_response
                    elif chat_response:
                        if pre_sanitised:
                            # Use pre-sanitised content
                            resp_message = chat_response
                            spoken_response = message_dict.get('spoken_response', chat_response)
                            behaviour_triggered = message_dict.get('behaviour_triggered', False)
                            logger.debug("Using pre-sanitised content from queue")
                        else:
                            # sanitise the chat_response to replace behaviour requests with full paths
                            chat_response, behaviour_triggered, spoken_response = self.expressions.sanitise_request(chat_response)
                            resp_message = chat_response
                            logger.debug("Performing sanitisation during speech processing")
                    
                    else:
                        logger.debug("Message does not contain 'chat_response'.")
                        if not is_chunk:
                            self.finish_speech_processing()
                        return

                except (SyntaxError, KeyError) as e:
                    logger.debug("Failed to decode message:", e)
                    if not is_chunk:
                        self.finish_speech_processing()
                    return
                
                # Strip brace segments (e.g. { ... }) from what will be spoken
                resp_message = self._strip_brace_segments(resp_message)
                if not resp_message:
                    logger.debug("Response empty after stripping brace segments. Cancelling speech segment.")
                    if not is_chunk:
                        self.finish_speech_processing()
                    return
                
                # Display and process the message
                logger.info("AI Inference Result:\n================================\n", resp_message, "\n================================\n")
                self.memory.raiseEvent("RunningBehaviour", True)
                
                # Mark speaking state and notify other modules (e.g. audio stream) BEFORE speaking
                # Only set Speaking True if not already speaking (to avoid audio stream toggle)
                if not self.is_currently_speaking:
                    self.is_currently_speaking = True
                    
                    # Generate speech ID if not provided
                    if not hasattr(self, '_current_speech_processing_id'):
                        self.speech_counter += 1
                        self._current_speech_processing_id = "speech_{}".format(self.speech_counter)
                    
                    # Notify speaking manager
                    self.memory.raiseEvent("StartSpeaking", self._current_speech_processing_id)
                    logger.debug("Notified speaking manager to start speaking")
                else:
                    logger.debug("Already speaking, not toggling Speaking event")

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
            logger.error("Error processing speech response:", e)
            if not is_chunk:
                self.finish_speech_processing()

    def finish_speech_processing(self):
        """Helper method to finish speech processing"""
        if hasattr(self, '_current_speech_processing_id'):
            self.memory.raiseEvent("StopSpeaking", self._current_speech_processing_id)
            delattr(self, '_current_speech_processing_id')

    def _strip_brace_segments(self, text):
        # Remove any { ... } segments (and leading whitespace before them), then collapse extra spaces
        cleaned = re.sub(r'\s*\{[^}]*\}', '', text)
        cleaned = re.sub(r' +', ' ', cleaned).strip()
        return cleaned
