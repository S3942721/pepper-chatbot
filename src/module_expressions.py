# -*- coding: utf-8 -*-
import json
import random
import re
from naoqi import ALProxy

class BehaviourExecutor:
    def __init__(self, behaviours_file):
        self.behaviours_file = behaviours_file
        with open(self.behaviours_file, 'r') as file:
            self.behaviours = json.load(file)

    def sanitize_behaviour_requests(self, chat_response):
        """
        Replace behaviour request keywords with full animation paths
        
        Finds the keywords in braces that are after the 'start', 'wait', 'stop', and 'run' keywords and replaces them with the full path to the animation.
        
        Example:
            "^start(hey) Goodbye ^wait(hey)” will become "^start(animations/Stand/Gestures/Hey_4) Goodbye ^wait(animations/Stand/Gestures/Hey_4)"
        """
        print("Sanitizing chat response: '{}'".format(chat_response))
        # Dictionary to store the mapping of keywords to selected behaviours
        keyword_to_behaviour = {}
        behaviour_triggered = [False]  # Use a list to allow modification in nested function

        # Function to replace keywords with full animation paths
        def replace_keyword(match):
            keyword = match.group(2)

            if keyword not in keyword_to_behaviour:
                # Search for the behaviour key in the behaviours
                behaviour = next((b for b in self.behaviours if b['behaviour_key'] == keyword), None)
                if behaviour:
                    selected_behaviour = random.choice(behaviour['behaviour_variations'])
                    keyword_to_behaviour[keyword] = selected_behaviour
                    print("Keyword '{}' mapped to behaviour: {}".format(keyword, selected_behaviour))
                    behaviour_triggered[0] = True
                else:
                    print("No behaviour found for keyword: '{}'".format(keyword))
                    return match.group(0)  # Return the original match if no behaviour is found
            return "^{}({})".format(match.group(1), keyword_to_behaviour[keyword])

        # Replace all occurrences of the keywords in the chat response
        sanitized_response = re.sub(r'\^(start|wait|stop|run)\((.*?)\)', replace_keyword, chat_response)
        
        # Remove behaviour actions to create spoken response
        spoken_response = re.sub(r'\^(start|wait|stop|run)\([^\)]*\)', '', chat_response).strip()
        
        print("Sanitized chat response: '{}'".format(sanitized_response))
        print("Spoken response: '{}'".format(spoken_response))
        return sanitized_response, behaviour_triggered[0], spoken_response

    def execute_behaviour(self, behaviour_key, nao_ip, nao_port):
        """
        Execute a behaviour based on the behaviour key
        
        The behaviour key is used to find the corresponding behaviour in the behaviours JSON file.
        The behaviour is selected randomly from the available variations.
        The full path to the animation is returned.
        """

        behaviour = next((b for b in self.behaviours if b['behaviour_key'] == behaviour_key), None)
        if behaviour:
            selected_behaviour = random.choice(behaviour['behaviour_variations'])
            print("Executing behaviour: {}".format(selected_behaviour))
            
            # Convert selected_behaviour to string if it is not
            if not isinstance(selected_behaviour, str):
                selected_behaviour = str(selected_behaviour)

            # Execute the behaviour using ALBehaviorManager
            try:
                animation_player_service = ALProxy("ALAnimationPlayer", nao_ip, nao_port)
                animation_player_service.run(selected_behaviour, _async=True)
                return selected_behaviour
            except Exception as e:
                print("Error executing behaviour: {}".format(e))
        else:
            print("No behaviour found for key: '{}'".format(behaviour_key))
        return None
    
    def execute_random_behaviour(self, behaviour_keys, nao_ip, nao_port):
        """
        Execute a behaviour based on multiple behaviour keys. It will pick a single random behaviour from the list of keys.
        
        The behaviour key is used to find the corresponding behaviour in the behaviours JSON file.
        The behaviour is selected randomly from the available variations.
        The full path to the animation is returned.
        """
        self.execute_behaviour(random.choice(behaviour_keys), nao_ip, nao_port)
        
        
# Example usage:
# executor = BehaviourExecutor('/path/to/behaviours.json')
# sanitized_response, behaviour_triggered = executor.sanitize_behaviour_requests("^start(hey) Goodbye ^wait(hey)")
# print(sanitized_response, behaviour_triggered)
# >> ^start(animations/Stand/Gestures/Hey_4) Goodbye ^wait(animations/Stand/Gestures/Hey_4) True
    def get_next_behaviour(self, index=0, previous_bhv_description="<NO DESCRIPTION>"):
        """
        Get the next behaviour in the sequence based on the previous one.
        
        This function will also update the description of the previous behaviour in the JSON file.
        
        Returns the next behaviour command and the next index.
        """
        def update_behaviour_description(current_index, description):
            """
            Update the description of the behaviour at the given index.
            """
            if 0 <= current_index < len(self.behaviours):
                current_description = self.behaviours[current_index].get('action_description', "<NO DESCRIPTION>")
                if current_description == "<NO DESCRIPTION>" or description != "<NO DESCRIPTION>":
                    self.behaviours[current_index]['action_description'] = description
                    with open(self.behaviours_file, 'w') as file:
                        json.dump(self.behaviours, file, indent=4)
                    print("Updated behaviour at index {} with description: {}".format(current_index, description))

        # Update the description of the previous behaviour if it was actually run
        if index > 0 and self.behaviours[index - 1].get('action_description', "<NO DESCRIPTION>") == "<NO DESCRIPTION>":
            update_behaviour_description(index - 1, previous_bhv_description)

        # Find the next behaviour without a description
        while index < len(self.behaviours):
            behaviour = self.behaviours[index]
            if behaviour.get('action_description', "<NO DESCRIPTION>") == "<NO DESCRIPTION>":
                return "{} ^run({})".format(behaviour['behaviour_key'], behaviour['behaviour_key']), index + 1
            else:
                print("Skipped: {}".format(behaviour['action_description']))
            index += 1

        return None, index
