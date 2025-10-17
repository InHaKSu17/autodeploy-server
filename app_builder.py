import os
import sys
import json
import base64
import time
from threading import Thread
import requests
from flask import Flask, request, jsonify

# --- 1. STARTUP SELF-DIAGNOSTIC ---
def check_environment_variables():
    """
    Checks for all required environment variables at startup.
    If any are missing, it prints a clear error and exits.
    """
    print("--- Running Startup Environment Check ---")
    required_vars = ['MY_SECRET', 'GITHUB_TOKEN', 'GITHUB_USERNAME']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"FATAL ERROR: The following environment variables are MISSING:")
        for var in missing_vars:
            print(f"  - {var}")
        print("Please set these variables in the Render Environment tab and redeploy.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # Exit the application with a failure code. Render will show it crashed.
        sys.exit(1)
        
    print("SUCCESS: All required environment variables are present.")
    
# Run the check immediately when the script starts
check_environment_variables()

# --- 2. Configuration & Setup ---
MY_SECRET = os.environ.get('MY_SECRET')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME')

MIT_LICENSE_TEXT = """
MIT License
Copyright (c) 2025 Your Name
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

app = Flask(__name__)

# --- 3. API Endpoints ---

@app.route('/', methods=['GET'])
def health_check():
    """A simple health check endpoint to confirm the server is running."""
    print("--- Health Check Endpoint Hit ---")
    return jsonify({"status": "ok", "message": "Server is running and healthy."}), 200

@app.route('/debug-env', methods=['GET'])
def debug_env():
    """A public endpoint to safely check if environment variables are loaded."""
    print("--- Running Debug Check ---")
    token = os.environ.get('GITHUB_TOKEN')
    report = {
        "MY_SECRET": "Set" if os.environ.get('MY_SECRET') else "!!! MISSING !!!",
        "GITHUB_TOKEN": "Set" if token else "!!! MISSING !!!",
        "GITHUB_USERNAME": "Set" if os.environ.get('GITHUB_USERNAME') else "!!! MISSING !!!",
    }
    if token and token.startswith('ghp_'):
        report["GITHUB_TOKEN_FORMAT"] = "Looks Correct (starts with ghp_)"
    elif token:
        report["GITHUB_TOKEN_FORMAT"] = "!!! INCORRECT FORMAT !!!"
    return jsonify(report), 200

@app.route('/api-endpoint', methods=['POST'])
def handle_request():
    """The main endpoint that receives the project brief."""
    print("\n\n=== Received a new request ===")
    request_data = request.json
    if not MY_SECRET or request_data.get('secret') != MY_SECRET:
        print("Error: Unauthorized. Invalid or missing secret.")
        return jsonify({"error": "Unauthorized"}), 401
    thread = Thread(target=process_task_async, args=(request_data,))
    thread.start()
    print("Request authenticated. Acknowledged with 200 OK. Starting background processing.")
    return jsonify({"status": "Request received and is being processed."}), 200

# --- 4. Core Application Logic (Functions) ---

def process_task_async(task_data):
    """The main background process to handle a task."""
    try:
        print("--- Background thread started successfully. ---")
        task_id = task_data['task']
        # ... (The rest of your functions are unchanged) ...
        round_num = task_data['round']
        brief = task_data['brief']
        attachments = task_data.get('attachments', [])
        
        print(f"--- Starting processing for task: {task_id}, Round: {round_num} ---")

        existing_code = None
        if round_num > 1:
            try:
                repo_details = create_or_update_github_repo(task_id, round_num, {})
                existing_code = repo_details.get('existing_code')
            except Exception as e:
                print(f"Error pre-fetching code for Round 2: {e}")

        app_files = generate_app_with_llm(brief, attachments, round_num, existing_code)
        if not app_files: raise ValueError("LLM failed to generate valid files.")

        repo_details = create_or_update_github_repo(task_id, round_num, app_files)

        notification_payload = {
            "email": task_data['email'],
            "task": task_id,
            "round": round_num,
            "nonce": task_data['nonce'],
            "repo_url": repo_details['repo_url'],
            "commit_sha": repo_details['commit_sha'],
            "pages_url": repo_details['pages_url'],
        }

        notify_evaluator(task_data['evaluation_url'], notification_payload)
        print(f"--- Successfully completed processing for task: {task_id}, Round: {round_num} ---")

    except Exception as e:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"FATAL ERROR in background thread: {e}")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# (All other functions like generate_app_with_llm, create_or_update_github_repo, etc. go here)
def generate_app_with_llm(brief, attachments, round_num, existing_code=None):
    print("Connecting to Gemini API...")
    # ... Omitted for brevity, but this function should be here in your file
    return {"index.html": "<h1>Hello</h1>", "README.md": "# Test"}

def create_or_update_github_repo(repo_name, round_num, files_to_commit):
    print(f"Starting GitHub operations for repo: {repo_name}")
    # ... Omitted for brevity, but this function should be here in your file
    return {"repo_url": "url", "commit_sha": "sha", "pages_url": "url", "existing_code": "code"}

def notify_evaluator(evaluation_url, payload):
    print(f"Notifying evaluation server at: {evaluation_url}")
    # ... Omitted for brevity, but this function should be here in your file
    return

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
```
*(Note: I've included placeholder stubs for the core logic functions to keep the example clean, but you should use the full functions from our previous conversations in your final file.)*

---

### Part 2: A Clean Slate Deployment on Render

To avoid any old, broken settings, we will delete the old service and create a new one.

1.  **Delete the Old Service:** Go to your Render Dashboard, find your `autodeploy-server` service, click on it, go to the **"Settings"** tab, scroll to the bottom, and click the red **"Delete Service"** button.
2.  **Create a New Service:** Click **New +** -> **Web Service** and connect your `autodeploy-server` GitHub repository again.
3.  **Configure It:** Use the same settings as before.
    * **Name:** `autodeploy-server-v2` (use a new name)
    * **Runtime:** `Python 3`
    * **Build Command:** `pip install -r requirements.txt`
    * **Start Command:** `gunicorn app_builder:app`
4.  **CRITICAL STEP: Set Environment Variables:** Go to the **"Environment"** tab. **Triple-check every character** as you add your three secrets: `MY_SECRET`, `GITHUB_TOKEN`, and `GITHUB_USERNAME`. Ensure there are no extra spaces.
5.  Click **"Create Web Service"**.

---

### Part 3: The Foolproof Testing Plan

This is a two-step process. Only proceed to step 2 if step 1 is successful.

#### Test 1: The Health Check (Is the server running?)

This test checks if your server started correctly without crashing.

* **Action:** Run this simple `curl` command in your terminal, replacing the URL with your new one.
    ```bash
    curl https://autodeploy-server-v2.onrender.com/
    ```
* **Expected Result:** You should see this immediately:
    ```json
    {"status":"ok","message":"Server is running and healthy."}
    ```

* **If it fails (e.g., "connection closed"):**
    1.  Go to the **"Logs"** tab for your new service on Render.
    2.  You will see the `FATAL ERROR` message from our new startup check, telling you exactly which environment variable is wrong.
    3.  Go to the "Environment" tab, fix the typo, and Render will redeploy. Try the health check again.

#### Test 2: The Functional Test (Does the app work?)

Once the Health Check passes, your server is running. Now, test the actual assignment logic.

* **Action:** Run the full `curl` command in a single line. (Use the correct version for your shell from our previous conversation, and remember to replace the URL and your secret password).

    *For PowerShell/macOS/Linux:*
    ```bash
    curl -X POST https://autodeploy-server-v2.onrender.com/api-endpoint -H "Content-Type: application/json" -d '{"email": "final-test@example.com", "secret": "YOUR_SECRET_PASSWORD_HERE", "task": "final-test-run", "round": 1, "nonce": "final-nonce-456", "brief": "Final test with new code.", "evaluation_url": "https://httpbin.org/post"}'
    

