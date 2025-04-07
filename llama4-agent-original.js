const fs = require('fs');
const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

// Set your API keys
const RUNPOD_API_KEY = '...'; // API key for UI-Tars
const TOGETHER_API_KEY = '...'; // API key for Llama4

// Global variable to store interaction history
let interactionHistory = '---\n\nINTERACTION HISTORY:\n';

// Capture a screenshot using scrot (assumes scrot is installed)
async function captureScreenshot() {
  // The screenshot is saved as "screenshot.png"
  await execAsync('scrot --overwrite -o screenshot.png');
  return 'screenshot.png';
}

// Load an image file and convert it to a base64 string
async function loadImageAsBase64(filename) {
  const buffer = fs.readFileSync(filename);
  return buffer.toString('base64');
}

// Call the Llama4 API with the screenshot (as base64)
async function callLlama4API(base64Image) {
  console.log(interactionHistory);
  const systemPrompt = fs.readFileSync("llama4-prompt.txt").toString();
  
  const body = {
    model: "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
    messages: [
      {
        role: "system",
        content: systemPrompt
      },
      {
        role: "user",
        content: [
          { 
            type: "text", 
            text: "User objective: Show me what apple.com looked like in 2018."
          },
          {
            type: "image_url",
            image_url: {
              url: `data:image/png;base64,${base64Image}`
            }
          },
          {
            type: "text",
            text: `Interaction History:\n${interactionHistory}`
          }
        ]
      }
    ],
    temperature: 0.2,
    max_tokens: 8192
  };

  const response = await fetch("https://api.together.xyz/v1/chat/completions", {
    method: "post",
    body: JSON.stringify(body),
    headers: {
      "Authorization": `Bearer ${TOGETHER_API_KEY}`,
      "Content-Type": "application/json"
    }
  });
  
  return await response.json();
}

// Call the UI-Tars API with the provided element description and image
async function callUITarsAPI(elementDescription, base64Image) {
  const body = {
    model: "bytedance-research/UI-TARS-7B-DPO",
    messages: [
      {
        role: "system",
        content: "Assist the user in pointing out the specified UI element in the given image, being as accurate as possible. Your response will only comprise the coordinates in form (x,y). It is crucial that you select the correct UI element, and not necessarily anything else that may be 'nearby' or 'close'."
      },
      {
        role: "user",
        content: [
          {
            type: "text",
            text: elementDescription
          },
          {
            type: "image_url",
            image_url: {
              url: "data:image/png;base64," + base64Image
            }
          }
        ]
      }
    ],
    temperature: 0,
    max_tokens: 2048
  };

  const response = await fetch('https://api.runpod.ai/v2/227oaj96knqxa7/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${RUNPOD_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });

  const txt = await response.text();
  return JSON.parse(txt);
}

// Extract coordinates from a text in the format (x,y)
function parseCoordinatesFromText(text) {
  const regex = /\((\d+\.?\d*),\s*(\d+\.?\d*)\)/;
  const match = text.match(regex);
  if (match) {
    return { x: parseFloat(match[1]), y: parseFloat(match[2]) };
  }
  return null;
}

// Scale coordinates normalized for a 1000x1000 image to real dimensions 1600x900
function scaleCoordinates(normalizedCoords) {
  const xReal = (normalizedCoords.x / 1000) * 1600;
  const yReal = (normalizedCoords.y / 1000) * 900;
  return { x: Math.round(xReal), y: Math.round(yReal) };
}

// Use xdotool to perform a click at (x, y)
async function performClick(x, y) {
  await execAsync(`xdotool mousemove ${x} ${y} click 1`);
}

// Simulate typing using xdotool: ctrl+a, backspace, then type text (with 250ms pauses)
async function performType(text, pressEnter) {
  await execAsync(`xdotool key ctrl+a`);
  await new Promise(resolve => setTimeout(resolve, 250));
  await execAsync(`xdotool key BackSpace`);
  await new Promise(resolve => setTimeout(resolve, 250));
  await execAsync(`xdotool type "${text}"`);
  if (pressEnter) {
    await new Promise(resolve => setTimeout(resolve, 250));
    await execAsync(`xdotool key Return`);
  }
}

// A generic wait function
async function performWait(seconds) {
  await new Promise(resolve => setTimeout(resolve, seconds * 1000));
}

// Extract function calls from Llama4's response format
function extractFunctionCall(content) {
  const match = content.split("===FUNCTION===")
  
  if (match && match[1]) {
    try {
      const functionData = JSON.parse(match[1]);
      return {
        name: functionData.function,
        args: functionData.parameters
      };
    } catch (err) {
      console.error('Error parsing function call JSON:', err);
      return null;
    }
  }
  return null;
}

// Process the Llama4 API response, executing actions based on text and function calls
// Returns true if a stop command is received
async function processLlama4Response(response, base64Image) {
  let stopLoop = false;
  
  if (!response.choices || response.choices.length === 0) {
    console.error('No choices in Llama4 response.');
    return stopLoop;
  }
  
  // Process only the first choice
  const choice = response.choices[0];
  const content = choice.message.content;
  
  console.log('Response content:', content);
  
  // Extract the function call
  const functionCall = extractFunctionCall(content);
  
  if (functionCall) {
    const { name, args } = functionCall;
    console.log(`Function call: ${name} with args:`, args);
    
    // Add the response to interaction history
    const responseText = content.replace(/<function>[\s\S]*?<\/function>/, '').trim();
    interactionHistory += `Reasoning: ${responseText}\n\n`;
    
    switch (name) {
      case 'computer_click': {
        // Pass the element description to UI-Tars
        const elementDescription = args.elementDescription;
        const uiTarsResponse = await callUITarsAPI(elementDescription, base64Image);
        
        if (uiTarsResponse.choices && uiTarsResponse.choices.length > 0) {
          // Concatenate text parts from UI-Tars response
          const uiTarsText = uiTarsResponse.choices[0].message.content;
          const normalizedCoords = parseCoordinatesFromText(uiTarsText);
          
          if (normalizedCoords) {
            const realCoords = scaleCoordinates(normalizedCoords);
            console.log('Clicking at:', realCoords);
            await performClick(realCoords.x, realCoords.y);
            interactionHistory += `Action: Clicked on element "${elementDescription}" at coordinates (${realCoords.x}, ${realCoords.y})\n\n`;
          } else {
            console.error('Unable to parse coordinates from UI-Tars response:', uiTarsText);
            interactionHistory += `Error: Unable to find coordinates for "${elementDescription}"\n\n`;
          }
        } else {
          console.error('No candidates from UI-Tars API.');
          interactionHistory += `Error: No response from UI-Tars for "${elementDescription}"\n\n`;
        }
        break;
      }
      case 'computer_type': {
        const typeText = args.text;
        const pressEnter = args.pressEnter;
        await performType(typeText, pressEnter);
        interactionHistory += `Action: Typed "${typeText}" ${pressEnter ? 'and pressed Enter' : ''}\n\n`;
        break;
      }
      case 'computer_click_and_type': {
        const elementDescription = args.elementDescription;
        const typeText = args.text;
        const pressEnter = args.pressEnter;
        
        const uiTarsResponse = await callUITarsAPI(elementDescription, base64Image);
        
        if (uiTarsResponse.choices && uiTarsResponse.choices.length > 0) {
          const uiTarsText = uiTarsResponse.choices[0].message.content;
          const normalizedCoords = parseCoordinatesFromText(uiTarsText);
          
          if (normalizedCoords) {
            const realCoords = scaleCoordinates(normalizedCoords);
            console.log('Clicking at:', realCoords);
            await performClick(realCoords.x, realCoords.y);
            await performWait(0.5);
            await performType(typeText, pressEnter);
            interactionHistory += `Action: Clicked on "${elementDescription}" and typed "${typeText}" ${pressEnter ? 'with Enter' : ''}\n\n`;
          } else {
            console.error('Unable to parse coordinates from UI-Tars response');
            interactionHistory += `Error: Unable to find coordinates for "${elementDescription}"\n\n`;
          }
        } else {
          console.error('No candidates from UI-Tars API.');
          interactionHistory += `Error: No response from UI-Tars for "${elementDescription}"\n\n`;
        }
        break;
      }
      case 'wait': {
        const seconds = args.seconds;
        await performWait(seconds);
        interactionHistory += `Action: Waited for ${seconds} seconds\n\n`;
        break;
      }
      case 'stop': {
        stopLoop = true;
        console.log('Stop command received with result:', args.result);
        interactionHistory += `Action: Stopped with result: ${args.result}\n\n`;
        break;
      }
      case 'note': {
        console.log('Note:', args.note);
        interactionHistory += `Note: ${args.note}\n\n`;
        break;
      }
      case 'user_message': {
        console.log('User message:', args.message);
        interactionHistory += `Message to user: ${args.message}\n\n`;
        // Implement a blocking prompt here if needed
        break;
      }
      default:
        console.log('Unknown function call:', name);
        interactionHistory += `Error: Unknown function "${name}"\n\n`;
    }
  } else {
    console.log('No function call found in the response');
    interactionHistory += `Response without function call: ${content}\n\n`;
  }

  console.log("wait");
  await performWait(5);
  console.log("waited");
  await performWait(1);
  
  return stopLoop;
}

// The main agent loop
async function main() {
  let stopAgent = false;
  let iterationCount = 0;
  
  while (!stopAgent && iterationCount < 50) { // Add safety iteration limit
    try {
      console.log(`\n--- Iteration ${iterationCount + 1} ---`);
      
      // 1. Capture a screenshot
      const screenshotFile = await captureScreenshot();
      console.log('Screenshot captured:', screenshotFile);
      
      // 2. Convert the screenshot to base64
      const base64Image = await loadImageAsBase64(screenshotFile);
      console.log('Screenshot converted to base64');
      
      // 3. Call Llama4 API with the base64 image
      console.log('Calling Llama4 API...');
      const llama4Response = await callLlama4API(base64Image);
      
      // 4. Process the response and execute any actions
      console.log('Processing Llama4 response...');
      stopAgent = await processLlama4Response(llama4Response, base64Image);
      
      iterationCount++;
    } catch (err) {
      console.error('Error in agent loop:', err);
      interactionHistory += `Error in agent loop: ${err.message}\n\n`;
    }
    
    // Wait 3 seconds before repeating, unless a stop was received
    if (!stopAgent) {
      console.log('Waiting 5 seconds before next iteration...');
      await performWait(3);
    }
  }
  
  if (iterationCount >= 50) {
    console.log('Agent stopped after reaching maximum iterations.');
    interactionHistory += 'Agent stopped after reaching maximum iterations.\n\n';
  } else {
    console.log('Agent stopped as requested.');
  }
  
  // Write the interaction history to a file
  fs.writeFileSync('interaction_history.txt', interactionHistory);
  console.log('Interaction history saved to interaction_history.txt');
}

main();
