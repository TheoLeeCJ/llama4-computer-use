import json
import base64
import os
import time
import subprocess
from pathlib import Path
import requests
from datetime import datetime

class Llama4Agent:
    def __init__(self):
        self.interaction_history = "---\n\nINTERACTION HISTORY:\n"
        self.step_counter = 1
        self.load_config()
        self.load_prompt()
        self.setup_run_directory()
        
    def setup_run_directory(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path("past_runs") / timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_counter = 1
        
    def show_warning(self):
        with open("warning.txt") as f:
            warning = f.read()
        print("\n" + "="*80)
        print(warning)
        print("="*80 + "\n")
        return True
                
    def get_user_task(self):
        print("\nWhat would you like the agent to do?")
        return input("Enter task: ").strip()

    def load_config(self):
        with open("config.json") as f:
            self.config = json.load(f)
            
    def load_prompt(self):
        # Load the base prompt
        with open("llama4-prompt.txt") as f:
            prompt_text = f.read()
            
        # Load all tool JSONs from prompts directory
        tools = []
        prompts_dir = Path("prompts")
        for json_file in prompts_dir.glob("*.json"):
            print(f"Loaded {json_file}")
            with open(json_file) as f:
                tools.append(json.load(f))
                
        # Replace placeholder with tools array
        self.system_prompt = prompt_text.replace(
            "TOOLS_INSERTED_HERE", 
            "\n```\n" + json.dumps(tools, indent=2) + "\n```\n"
        )

    def capture_screenshot(self):
        screenshot_path = self.run_dir / f"screenshot_{self.screenshot_counter:03d}.png"
        subprocess.run(["scrot", "--overwrite", "-o", str(screenshot_path)], check=True)
        self.screenshot_counter += 1
        return str(screenshot_path)

    def load_image_as_base64(self, filename):
        with open(filename, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def call_llama4_api(self, base64_image):
        print(self.interaction_history)
        
        body = {
            "model": self.config["llama4ModelName"],
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"User objective: {self.user_objective}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text", 
                            "text": f"Interaction History:\n<interaction_history>\n{self.interaction_history}</interaction_history>"
                        }
                    ]
                }
            ],
            "temperature": 0.2,
            "max_tokens": 8192
        }

        response = requests.post(
            f"{self.config['llama4ApiUrl']}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config['llama4ApiKey']}",
                "Content-Type": "application/json"
            },
            json=body
        )
        return response.json()

    def call_uitars_api(self, element_description, base64_image):
        body = {
            "model": self.config["uitarsModelName"],
            "messages": [
                {
                    "role": "system",
                    "content": "Assist the user in pointing out the specified UI element in the given image, being as accurate as possible. Your response will only comprise the coordinates in form (x,y). It is crucial that you select the correct UI element, and not necessarily anything else that may be 'nearby' or 'close'."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": element_description
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0,
            "max_tokens": 2048
        }

        response = requests.post(
            f"{self.config['uitarsApiUrl']}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config['uitarsApiKey']}",
                "Content-Type": "application/json"
            },
            json=body
        )
        return response.json()

    def parse_coordinates(self, text):
        import re
        match = re.search(r'\((\d+\.?\d*),\s*(\d+\.?\d*)\)', text)
        if match:
            return {"x": float(match.group(1)), "y": float(match.group(2))}
        return None

    def scale_coordinates(self, normalized_coords):
        screen_width, screen_height = self.config["realScreenSize"]
        x_real = (normalized_coords["x"] / 1000) * screen_width
        y_real = (normalized_coords["y"] / 1000) * screen_height
        return {"x": round(x_real), "y": round(y_real)}

    def perform_click(self, x, y):
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"], check=True)

    def perform_type(self, text, press_enter):
        subprocess.run(["xdotool", "key", "ctrl+a"], check=True)
        time.sleep(0.25)
        subprocess.run(["xdotool", "key", "BackSpace"], check=True)
        time.sleep(0.25)
        subprocess.run(["xdotool", "type", text], check=True)
        if press_enter:
            time.sleep(0.25)
            subprocess.run(["xdotool", "key", "Return"], check=True)

    def perform_scroll(self, x, y, direction, clicks=1):
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], check=True)
        time.sleep(0.25)
        button = "4" if direction == "up" else "5"
        for _ in range(clicks):
            subprocess.run(["xdotool", "click", button], check=True)
            time.sleep(0.1)

    def extract_function_call(self, content):
        parts = content.split("===FUNCTION===")
        if len(parts) > 1:
            try:
                function_data = json.loads(parts[1])
                return {
                    "name": function_data["function"],
                    "args": function_data["parameters"]
                }
            except json.JSONDecodeError as e:
                print(f"Error parsing function call JSON: {e}")
                return None
        return None

    def handle_user_message(self, message, is_login):
        print("\n" + "="*50)
        print(message)
        print("="*50)
        
        while True:
            response = input("\nContinue? (y/n): ").lower()
            if response == 'y':
                return True
            elif response == 'n':
                return False

    def format_function_call(self, name, args):
        return json.dumps({"function": name, "parameters": args}, indent=2)

    def handle_user_action_review(self, name, args):
        print("\n" + "="*50)
        print("Proposed Action:")
        print(f"Function: {name}")
        print("Parameters:")
        print(self.format_function_call(name, args))
        print("="*50)
        
        while True:
            choice = input("\nAccept [press A] / Reject (type reason): ").strip()
            if choice.lower() == 'a':
                return True
            elif choice:
                self.interaction_history += f"\n\nAction rejected: {choice}\n\n"
                return False

    def extract_interaction_summary(self, content):
        import re
        pattern = r'<int_summary>(.*?)</int_summary>'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    async def process_llama4_response(self, response, base64_image):
        stop_loop = False
        
        if not response.get("choices"):
            print("No choices in Llama4 response.")
            return stop_loop
            
        choice = response["choices"][0]
        content = choice["message"]["content"]
        print("Response content:", content)
        
        function_call = self.extract_function_call(content)
        
        if function_call:
            name = function_call["name"]
            args = function_call["args"]
            print(f"Function call: {name} with args:", args)
            
            # Extract summary if available, otherwise use full response
            summary = self.extract_interaction_summary(content)
            if summary:
                self.interaction_history += f"Step {self.step_counter}: {summary}\n"
                self.step_counter += 1
            else:
                response_text = content.split("===FUNCTION===")[0].strip()
                self.interaction_history += f"Step {self.step_counter}: {response_text}\n"
                self.step_counter += 1
            
            # Add function call to history
            self.interaction_history += f"Action: {self.format_function_call(name, args)}\n\n"
            
            if not self.handle_user_action_review(name, args):
                return False
            
            if name == "computer_click":
                element_description = args["elementDescription"]
                uitars_response = self.call_uitars_api(element_description, base64_image)
                
                if uitars_response.get("choices"):
                    uitars_text = uitars_response["choices"][0]["message"]["content"]
                    normalized_coords = self.parse_coordinates(uitars_text)
                    
                    if normalized_coords:
                        real_coords = self.scale_coordinates(normalized_coords)
                        print("Clicking at:", real_coords)
                        self.perform_click(real_coords["x"], real_coords["y"])
                        self.interaction_history += f'Action: Clicked on element "{element_description}" at coordinates ({real_coords["x"]}, {real_coords["y"]})\n\n'
                    else:
                        print(f"Unable to parse coordinates from UI-Tars response: {uitars_text}")
                        self.interaction_history += f'Error: Unable to find coordinates for "{element_description}"\n\n'
                        
            elif name == "computer_type":
                self.perform_type(args["text"], args["pressEnter"])
                self.interaction_history += f'Action: Typed "{args["text"]}" {"and pressed Enter" if args["pressEnter"] else ""}\n\n'
                
            elif name == "computer_click_and_type":
                element_description = args["elementDescription"]
                uitars_response = self.call_uitars_api(element_description, base64_image)
                
                if uitars_response.get("choices"):
                    uitars_text = uitars_response["choices"][0]["message"]["content"]
                    normalized_coords = self.parse_coordinates(uitars_text)
                    
                    if normalized_coords:
                        real_coords = self.scale_coordinates(normalized_coords)
                        print("Clicking at:", real_coords)
                        self.perform_click(real_coords["x"], real_coords["y"])
                        time.sleep(0.5)
                        self.perform_type(args["text"], args["pressEnter"])
                        self.interaction_history += f'Action: Clicked on "{element_description}" and typed "{args["text"]}" {"with Enter" if args["pressEnter"] else ""}\n\n'
                        
            elif name == "computer_scroll":
                element_description = args["elementDescription"]
                direction = args["direction"]
                clicks = 2
                
                uitars_response = self.call_uitars_api(element_description, base64_image)
                
                if uitars_response.get("choices"):
                    uitars_text = uitars_response["choices"][0]["message"]["content"]
                    normalized_coords = self.parse_coordinates(uitars_text)
                    
                    if normalized_coords:
                        real_coords = self.scale_coordinates(normalized_coords)
                        print(f"Scrolling {direction} at:", real_coords)
                        self.perform_scroll(real_coords["x"], real_coords["y"], direction, clicks)
                        self.interaction_history += f'Action: Scrolled {direction} {clicks} times over "{element_description}" at coordinates ({real_coords["x"]}, {real_coords["y"]})\n\n'
                    else:
                        print(f"Unable to parse coordinates from UI-Tars response: {uitars_text}")
                        self.interaction_history += f'Error: Unable to find coordinates for "{element_description}"\n\n'
                        
            elif name == "wait":
                time.sleep(args["seconds"])
                self.interaction_history += f'Action: Waited for {args["seconds"]} seconds\n\n'
                
            elif name == "stop":
                stop_loop = True
                print("Stop command received with result:", args["result"])
                self.interaction_history += f'Action: Stopped with result: {args["result"]}\n\n'
                
            elif name == "note":
                print("Note:", args["note"])
                self.interaction_history += f'Note: {args["note"]}\n\n'
                
            elif name == "user_message":
                should_continue = self.handle_user_message(
                    args["message"], 
                    args.get("isLogin", False)
                )
                if not should_continue:
                    stop_loop = True
                self.interaction_history += f'Message to user: {args["message"]}\n\n'
                
        else:
            print("No function call found in the response")
            self.interaction_history += f"Response without function call: {content}\n\n"
        
        return stop_loop

    async def run(self):
        if not self.show_warning():
            print("Agent execution cancelled.")
            return
            
        task = self.get_user_task()
        self.user_objective = task
        
        stop_agent = False
        iteration_count = 0
        max_steps = self.config.get("maxSteps", 50)  # Default to 50 if not specified
        
        while not stop_agent and iteration_count < max_steps:
            try:
                print(f"\n--- Iteration {iteration_count + 1} ---")
                
                screenshot_file = self.capture_screenshot()
                print("Screenshot captured:", screenshot_file)
                
                base64_image = self.load_image_as_base64(screenshot_file)
                print("Screenshot converted to base64")
                
                print("Calling Llama4 API...")
                llama4_response = self.call_llama4_api(base64_image)
                
                print("Processing Llama4 response...")
                stop_agent = await self.process_llama4_response(llama4_response, base64_image)
                
                iteration_count += 1
                
            except Exception as e:
                print(f"Error in agent loop: {e}")
                self.interaction_history += f"Error in agent loop: {str(e)}\n\n"

            with open(self.run_dir / "interaction_history.txt", "w") as f:
                f.write(f"TASK: {self.user_objective}\n\n=====\n\n")
                f.write(self.interaction_history)
            print("Updated interaction history.")
            
            if not stop_agent:
                print("Waiting 7 seconds before next iteration...")
                time.sleep(7)
        
        if iteration_count >= max_steps:
            print(f"Agent stopped after reaching maximum iterations ({max_steps}).")
            self.interaction_history += f"Agent stopped after reaching maximum iterations ({max_steps}).\n\n"
        else:
            print("Agent stopped as requested.")

if __name__ == "__main__":
    import asyncio
    agent = Llama4Agent()
    asyncio.run(agent.run())
