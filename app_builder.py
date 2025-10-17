import os
import sys
import json
import base64
import time
from threading import Thread
import requests
import openai  # <-- ADDED: OpenAI library
from flask import Flask, request, jsonify

# --- 1. STARTUP SELF-DIAGNOSTIC ---
def check_environment_variables():
    """Checks for all required environment variables at startup."""
    print("--- Running Startup Environment Check ---")
    # MODIFIED: Added OPENAI_API_KEY to the required variables
    required_vars = ['MY_SECRET', 'GITHUB_TOKEN', 'GITHUB_USERNAME', 'OPENAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"FATAL ERROR: The following environment variables are MISSING:")
        for var in missing_vars:
            print(f"  - {var}")
        print("Please set these variables in your environment and redeploy.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        sys.exit(1)

    print("SUCCESS: All required environment variables are present.")

check_environment_variables()

# --- 2. Configuration & Setup ---
MY_SECRET = os.environ.get('MY_SECRET')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') # <-- ADDED: Get OpenAI key

# Initialize the OpenAI client globally
try:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    print("OpenAI client initialized successfully.")
except Exception as e:
    print(f"FATAL ERROR: Could not initialize OpenAI client: {e}")
    sys.exit(1)


MIT_LICENSE_TEXT = """
MIT License
Copyright (c) 2025 Your Name Harshabardhan Kashyap
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

# --- 3. API Endpoints (UNCHANGED) ---

@app.route('/', methods=['GET'])
def health_check():
    """A simple health check endpoint to confirm the server is running."""
    print("--- Health Check Endpoint Hit ---")
    return jsonify({"status": "ok", "message": "Server is running and healthy."}), 200

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
    """The main background process to handle a task. (UNCHANGED)"""
    try:
        print("--- Background thread started successfully. ---")
        task_id = task_data['task']
        round_num = task_data['round']
        brief = task_data['brief']
        attachments = task_data.get('attachments', [])

        print(f"--- Starting processing for task: {task_id}, Round: {round_num} ---")

        existing_code = None
        if round_num > 1:
            try:
                # Fetches existing code from the repo before calling the LLM
                repo_details = create_or_update_github_repo(task_id, round_num, {}, pre_fetch_code=True)
                existing_code = repo_details.get('existing_code')
            except Exception as e:
                print(f"Error pre-fetching code for Round 2: {e}")

        # The only change in this function is that the one below now calls OpenAI
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

# --- vvv ENTIRELY REWRITTEN FUNCTION vvv ---
def generate_app_with_llm(brief, attachments, round_num, existing_code=None):
    """Calls the OpenAI API to generate application code based on a brief."""
    print("Connecting to OpenAI API to generate code...")

    # Prepare attachments (this logic is unchanged)
    decoded_attachments = []
    for attachment in attachments:
        header, encoded_data = attachment['url'].split(',', 1)
        decoded_content = base64.b64decode(encoded_data).decode('utf-8', errors='ignore')
        decoded_attachments.append({"name": attachment['name'], "content": decoded_content})

    # Prepare the user-facing part of the prompt
    if round_num > 1 and existing_code:
        user_prompt_task = (f"Your task is to modify the provided 'index.html' file based on the new brief. The 'README.md' should also be updated to reflect the changes.\n\n--- NEW USER BRIEF ---\n{brief}\n------------------\n\n--- EXISTING index.html ---\n{existing_code}\n-------------------------\n")
    else:
        user_prompt_task = f"Your task is to generate two files: 'index.html' and 'README.md', based on the user's brief.\n--- USER BRIEF ---\n{brief}\n------------------\n"

    # Append attachment content to the user prompt
    if decoded_attachments:
        user_prompt_task += "\nThe application must use the following attached files:"
        for att in decoded_attachments:
            user_prompt_task += f"\n--- FILE: {att['name']} ---\n{att['content']}\n----------------------\n"

    # Define the system prompt to guide the AI's behavior and output format
    system_prompt = """
    You are an expert web developer specializing in creating single-file, production-ready applications.
    The 'index.html' file you create must be a single, complete HTML5 document. All CSS must be in a <style> tag and all JavaScript in a <script> tag.
    The 'README.md' must be professional and comprehensive.
    IMPORTANT: You must respond with ONLY a raw JSON object, without any surrounding text, explanations, or markdown formatting like ```json.
    The JSON object must have two string keys: "index.html" and "README.md".
    """

    try:
        print("Sending request to OpenAI model gpt-4-turbo...")
        chat_completion = openai_client.chat.completions.create(
            model="gpt-4-turbo",
            response_format={"type": "json_object"}, # Use OpenAI's JSON mode
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_task}
            ],
            temperature=0.7,
            timeout=120 # Increased timeout for complex generation
        )
        
        generated_text = chat_completion.choices[0].message.content
        generated_files = json.loads(generated_text) # The output is guaranteed to be a JSON string

        if "index.html" in generated_files and "README.md" in generated_files:
            print("Successfully received and parsed files from OpenAI.")
            return generated_files
        else:
            raise ValueError("OpenAI output did not contain the expected 'index.html' and 'README.md' keys.")

    except (openai.APIError, json.JSONDecodeError, ValueError) as e:
        print(f"An error occurred with the OpenAI API call or parsing: {e}")
        return None


def create_or_update_github_repo(repo_name, round_num, files_to_commit, pre_fetch_code=False):
    """
    Uses the GitHub API to create/update a repository and deploy to Pages.
    (MODIFIED to allow pre-fetching code without committing)
    """
    print(f"Starting GitHub operations for repo: {repo_name} (Round {round_num})")
    api_base_url = "[https://api.github.com](https://api.github.com)"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    repo_url = f"[https://github.com/](https://github.com/){GITHUB_USERNAME}/{repo_name}"
    latest_commit_sha = None
    existing_code = None

    # Logic to fetch existing code before the LLM call
    if pre_fetch_code:
        try:
            get_file_url = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/contents/index.html"
            file_res = requests.get(get_file_url, headers=headers, timeout=10)
            file_res.raise_for_status()
            existing_code = base64.b64decode(file_res.json()['content']).decode('utf-8')
            print("Successfully fetched existing index.html for revision.")
            return {"existing_code": existing_code} # Return early
        except requests.RequestException as e:
            print(f"Warning: Could not fetch existing index.html. Assuming it's the first commit for this file. Error: {e}")
            return {"existing_code": None}

    # Create repo if it's the first round
    if round_num == 1:
        payload = {"name": repo_name, "private": False, "description": "AI-generated project."}
        response = requests.post(f"{api_base_url}/user/repos", headers=headers, json=payload, timeout=10)
        if response.status_code == 201: print(f"Successfully created new repo: {repo_name}")
        elif response.status_code == 422: print(f"Repo '{repo_name}' already exists. Proceeding to update.")
        else: raise Exception(f"Failed to create repo. Status: {response.status_code}, Body: {response.text}")

    # Commit files to the repository
    files_to_commit['LICENSE'] = MIT_LICENSE_TEXT
    for filename, content in files_to_commit.items():
        upload_url = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/contents/{filename}"
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Check if file exists to get its SHA (for updating)
        sha = None
        get_file_res = requests.get(upload_url, headers=headers, timeout=10)
        if get_file_res.status_code == 200: sha = get_file_res.json().get('sha')
        
        upload_payload = {"message": f"feat: Round {round_num} - update {filename}", "content": encoded_content, "sha": sha}
        upload_response = requests.put(upload_url, headers=headers, json=upload_payload, timeout=20)
        
        if upload_response.status_code in [200, 201]:
            latest_commit_sha = upload_response.json()['commit']['sha']
            print(f"Successfully committed '{filename}'. New commit SHA: {latest_commit_sha}")
        else:
            raise Exception(f"Failed to commit {filename}. Status: {upload_response.status_code}, Body: {upload_response.text}")

    # Enable and wait for GitHub Pages deployment
    pages_url_api = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/pages"
    pages_payload = {"source": {"branch": "main", "path": "/"}}
    requests.post(pages_url_api, headers=headers, json=pages_payload, timeout=10)
    
    print("Waiting up to 2 minutes for GitHub Pages to deploy...")
    pages_live_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    for _ in range(12): # Poll for 2 minutes
        try:
            page_res = requests.head(pages_live_url, timeout=5)
            if page_res.status_code == 200:
                print(f"Deployment successful! Pages URL is live: {pages_live_url}")
                return {"repo_url": repo_url, "commit_sha": latest_commit_sha, "pages_url": pages_live_url}
        except requests.RequestException: pass
        time.sleep(10)
        
    print("Warning: Timed out waiting for Pages URL to become active, but returning URL anyway.")
    return {"repo_url": repo_url, "commit_sha": latest_commit_sha, "pages_url": pages_live_url}


def notify_evaluator(evaluation_url, payload):
    """Sends a POST request to the evaluation URL with exponential backoff retry. (UNCHANGED)"""
    print(f"Notifying evaluation server at: {evaluation_url}")
    max_retries, delay = 5, 1
    for attempt in range(max_retries):
        try:
            response = requests.post(evaluation_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
            response.raise_for_status()
            print(f"Successfully notified evaluator. Server responded with {response.status_code}.")
            return
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} to notify evaluator failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                print("Could not notify the evaluation server after multiple retries.")
                break

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
