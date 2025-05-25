import sys
import json
import subprocess
import urllib.parse
import logging

# Configure logging for the MCP server itself
# Log to stderr to avoid interfering with stdout JSON communication
logging.basicConfig(
    stream=sys.stderr, 
    level=logging.INFO, 
    format='%(asctime)s - MCP_SERVER - %(levelname)s - %(message)s'
)

def send_capabilities():
    capabilities = {
        "type": "tool_definitions", # This type is an assumption based on common patterns
        "tools": [
            {
                "name": "interact_with_telegram_bot",
                "description": (
                    "Opens Telegram desktop client to the '@ai_reminderbot' chat "
                    "and pre-fills a message. The user might need to press Send. "
                    "This tool is for testing the bot by sending it a message."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The message to send/pre-fill for '@ai_reminderbot'."
                        }
                    },
                    "required": ["message"]
                }
            }
        ]
    }
    try:
        print(json.dumps(capabilities), flush=True)
        logging.info("Sent capabilities.")
    except Exception as e:
        logging.error(f"Error sending capabilities: {e}")

def process_tool_call(tool_call):
    tool_name = tool_call.get("tool_name")
    call_id = tool_call.get("id")
    params = tool_call.get("params", {})

    response = {
        "type": "tool_error", # Default to error
        "id": call_id,
        "error": "Unknown tool or invalid request"
    }

    if tool_name == "interact_with_telegram_bot":
        message = params.get("message")
        if message is None:
            response["error"] = "Missing 'message' parameter."
        else:
            try:
                encoded_message = urllib.parse.quote(message)
                # Using 'open' command for macOS (darwin)
                # Format: tg://resolve?domain=USERNAME&text=MESSAGE
                command_url = f"tg://resolve?domain=ai_reminderbot&text={encoded_message}"
                
                logging.info(f"Executing: open \"{command_url}\"")
                
                process = subprocess.run(['open', command_url], 
                                         capture_output=True, text=True, check=False)

                if process.returncode == 0:
                    logging.info("Telegram URL opened successfully.")
                    response = {
                        "type": "tool_response",
                        "id": call_id,
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Successfully attempted to open Telegram to '@ai_reminderbot' "
                                    "and pre-fill your message. Please check Telegram and press "
                                    "Send if needed."
                                )
                            }
                        ]
                    }
                else:
                    error_message = (f"Failed to open Telegram URL. RC: {process.returncode}. "
                                     f"Stderr: {process.stderr}. Stdout: {process.stdout}")
                    logging.error(error_message)
                    response["error"] = f"Failed to open Telegram: {process.stderr or process.stdout or 'Unknown error'}"

            except FileNotFoundError:
                logging.error("'open' command not found. This tool relies on macOS.")
                response["error"] = "'open' command not found. Ensure you are on macOS."
            except subprocess.CalledProcessError as e:
                error_message = f"Error executing 'open' command: {e}. Stderr: {e.stderr}"
                logging.error(error_message)
                response["error"] = f"Error opening Telegram: {e.stderr or e}"
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}", exc_info=True)
                response["error"] = f"An unexpected error: {str(e)}"
    
    try:
        print(json.dumps(response), flush=True)
        logging.info(f"Sent response for call_id {call_id}") # Log less verbose response
    except Exception as e:
        logging.error(f"Error sending response for call_id {call_id}: {e}")


def main():
    logging.info("MCP Server starting...")
    send_capabilities()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            logging.info(f"Received line: {line}")
            try:
                request = json.loads(line)
                request_type = request.get("type")
                # Assuming tool calls will have a specific type, e.g., "tool_call"
                # This is an assumption as the protocol details for stdio were not fully specified.
                if request_type == "tool_call" and "tool_name" in request: 
                    process_tool_call(request)
                else:
                    logging.warning(f"Received non-tool_call or malformed request: {line}")
                    call_id = request.get("id")
                    if call_id: # Try to send an error if we have an ID
                        error_response = {
                            "type": "tool_error",
                            "id": call_id,
                            "error": "Unsupported request type or malformed tool_call."
                        }
                        print(json.dumps(error_response), flush=True)
            
            except json.JSONDecodeError:
                logging.error(f"Failed to decode JSON from stdin: {line}")
            except Exception as e:
                logging.error(f"Error processing request line '{line}': {e}", exc_info=True)
    
    except KeyboardInterrupt:
        logging.info("MCP Server shutting down (KeyboardInterrupt)...")
    except Exception as e:
        logging.error(f"MCP Server encountered a critical error: {e}", exc_info=True)
    finally:
        logging.info("MCP Server finished.")

if __name__ == "__main__":
    main() 