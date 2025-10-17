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
    """Checks for all required environment variables at startup."""
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
        sys.exit(1)
        
    print("SUCCESS: All required environment variables are present.")
    
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

def generate_app_with_llm(brief, attachments, round_num, existing_code=None):
    """Calls the Gemini API to generate application code based on a brief."""
    print("Connecting to Gemini API to generate code...")
    decoded_attachments = []
    for attachment in attachments:
        header, encoded_data = attachment['url'].split(',', 1)
        decoded_content = base64.b64decode(encoded_data).decode('utf-8', errors='ignore')
        decoded_attachments.append({"name": attachment['name'], "content": decoded_content})

    if round_num > 1 and existing_code:
        prompt_task = (f"Your task is to modify the provided 'index.html' file based on the new brief. The 'README.md' should also be updated to reflect the changes.\n\n--- NEW USER BRIEF ---\n{brief}\n------------------\n\n--- EXISTING index.html ---\n{existing_code}\n-------------------------\n")
    else:
        prompt_task = f"Your task is to generate two files: 'index.html' and 'README.md', based on the user's brief.\n--- USER BRIEF ---\n{brief}\n------------------\n"

    prompt_parts = ["You are an expert web developer specializing in creating single-file, production-ready applications.", prompt_task]
    if decoded_attachments:
        prompt_parts.append("The application must use the following attached files:")
        for att in decoded_attachments:
            prompt_parts.append(f"\n--- FILE: {att['name']} ---\n{att['content']}\n----------------------\n")

    prompt_parts.extend(["The 'index.html' file must be a single, complete HTML5 document. All CSS must be in a <style> tag and all JavaScript in a <script> tag, unless a CDN is explicitly required.", "The 'README.md' must be professional and comprehensive.", "IMPORTANT: You must respond with ONLY a raw JSON object, without any surrounding text, explanations, or markdown formatting.", 'The JSON object must have two string keys: "index.html" and "README.md".'])
    master_prompt = "\n".join(prompt_parts)
    
    api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent'
    payload = {"contents": [{"parts": [{"text": master_prompt}]}]}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        response_json = response.json()
        generated_text = response_json['candidates'][0]['content']['parts'][0]['text']
        generated_files = json.loads(generated_text)
        if "index.html" in generated_files and "README.md" in generated_files:
            print("Successfully received and parsed files from Gemini.")
            return generated_files
        else:
            raise ValueError("LLM output did not contain the expected file keys.")
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        print(f"An error occurred with the LLM API call or parsing: {e}")
        return None

def create_or_update_github_repo(repo_name, round_num, files_to_commit):
    """Uses the GitHub API to create/update a repository and deploy to Pages."""
    print(f"Starting GitHub operations for repo: {repo_name} (Round {round_num})")
    api_base_url = "https://api.github.com"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    latest_commit_sha = None
    existing_code = None

    if round_num > 1:
        try:
            get_file_url = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/contents/index.html"
            file_res = requests.get(get_file_url, headers=headers)
            file_res.raise_for_status()
            existing_code = base64.b64decode(file_res.json()['content']).decode('utf-8')
            print("Successfully fetched existing index.html for revision.")
        except requests.RequestException as e:
            print(f"Warning: Could not fetch existing index.html for round {round_num}. Error: {e}")

    if round_num == 1:
        payload = {"name": repo_name, "private": False, "description": "AI-generated project for autodeploy assignment."}
        response = requests.post(f"{api_base_url}/user/repos", headers=headers, json=payload)
        if response.status_code == 201: print(f"Successfully created new repo: {repo_name}")
        elif response.status_code == 422: print(f"Repo '{repo_name}' already exists. Proceeding to update.")
        else: raise Exception(f"Failed to create repo. Status: {response.status_code}, Body: {response.text}")

    files_to_commit['LICENSE'] = MIT_LICENSE_TEXT
    for filename, content in files_to_commit.items():
        upload_url = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/contents/{filename}"
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        sha = None
        get_file_res = requests.get(upload_url, headers=headers)
        if get_file_res.status_code == 200: sha = get_file_res.json().get('sha')
        upload_payload = {"message": f"feat: Round {round_num} - update {filename}", "content": encoded_content, "sha": sha}
        upload_response = requests.put(upload_url, headers=headers, json=upload_payload)
        if upload_response.status_code in [200, 201]:
            latest_commit_sha = upload_response.json()['commit']['sha']
            print(f"Successfully committed '{filename}'. New commit SHA: {latest_commit_sha}")
        else:
            raise Exception(f"Failed to commit {filename}. Status: {upload_response.status_code}, Body: {upload_response.text}")

    pages_url_api = f"{api_base_url}/repos/{GITHUB_USERNAME}/{repo_name}/pages"
    pages_payload = {"source": {"branch": "main", "path": "/"}}
    requests.post(pages_url_api, headers=headers, json=pages_payload)
    print("Waiting up to 2 minutes for GitHub Pages to deploy...")
    pages_live_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    for _ in range(12):
        try:
            page_res = requests.head(pages_live_url, timeout=5)
            if page_res.status_code == 200:
                print(f"Deployment successful! Pages URL is live: {pages_live_url}")
                return {"repo_url": repo_url, "commit_sha": latest_commit_sha, "pages_url": pages_live_url, "existing_code": existing_code}
        except requests.RequestException: pass
        time.sleep(10)
    print("Warning: Timed out waiting for Pages URL to become active.")
    return {"repo_url": repo_url, "commit_sha": latest_commit_sha, "pages_url": pages_live_url, "existing_code": existing_code}

def notify_evaluator(evaluation_url, payload):
    """Sends a POST request to the evaluation URL with exponential backoff retry."""
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
```

### Step 2: Push the Final Fix to GitHub

Now, let's upload this truly clean version.

1.  Save the `app_builder.py` file.
2.  Open your terminal in the project folder.
3.  Run these three commands:
    ```bash
    git add app_builder.py
    git commit -m "Final fix: Use verified clean code from file block"
    git push origin main
    ```

### Step 3: Watch the Final Deployment on Render

Go back to your service on Render. It will automatically detect the new push and start a new deployment.

This time, the `SyntaxError` will be gone. The first thing you should see in the **Logs** is:
```
--- Running Startup Environment Check ---
SUCCESS: All required environment variables are present.

