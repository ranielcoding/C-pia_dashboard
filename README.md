Cache warming and daily scheduling

Goal:
Ensure that expensive SQL queries used by the Streamlit app are executed automatically every day at 04:00 so the app process has those results cached (st.cache_data) before users first log in.

Approach:
1. A dedicated warming page was added: pages/_cache_warm.py
   - When visited it runs warm_all_caches() which executes the cache-decorated functions and populates the process cache.
   - Access can be restricted by a secret key stored in .streamlit/secrets.toml as warm_key.

2. The expensive, cache-decorated functions were moved to cache_loaders.py (project root) so both the app page and the warming page reuse the same cached functions.

How to schedule (Windows Task Scheduler):
- Create a scheduled task that runs daily at 04:00 and executes a PowerShell command or a script that requests the warming URL.
- Example PowerShell command (replace <secret>):

  powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8501/?page=_cache_warm&warm_key=<secret>' -UseBasicParsing"

- If you are using a PowerShell script file, run it with execution policy bypass:

  powershell -ExecutionPolicy Bypass -File "C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia\scripts\warm_cache.ps1" -Secret "<secret>"

- Steps quick guide:
  1. Open Task Scheduler
  2. Create Task -> General: choose an account (Run whether user is logged on)
  3. Triggers -> New -> Daily at 04:00
  4. Actions -> New -> Action: Start a program
     - Program/script: powershell
     - Add arguments: -ExecutionPolicy Bypass -File "C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia\scripts\warm_cache.ps1" -Secret "<secret>"
  5. Conditions: disable 'Start the task only if the computer is on AC power' if needed
  6. OK -> Save

Notes and caveats:
- The warming request must reach the same Streamlit process that serves users (same host and port). If multiple processes or containers are used, schedule a request for each instance/process.
- The Streamlit app must be running at 04:00 for warming to work. If the host may be down at that time, consider alternative approaches (hosting a separate script on the server that imports the functions directly, or orchestrating container restarts after warming).
- The warming page accepts an optional warm_key secret. Set it in .streamlit/secrets.toml like:

  [general]
  warm_key = "my-secret-key"

- TTL for the caches remains 24 hours. The scheduler will ensure that at 04:00 the cached values are refreshed.

Security:
- Do NOT commit .streamlit/secrets.toml to source control.
- If you cannot use a secret, restrict network access to the warming URL to internal network only.

Files changed/added:
- Added cache_loaders.py (new): moved cache-decorated data-loading functions and warm_all_caches()
- Added pages/_cache_warm.py (new): warming endpoint page
- Modified pages/page_venda_geral.py: imports updated to use cache_loaders (removed per-session reset logic)
- Added this README.md documenting scheduling steps

If you want, the assistant can now:
- Update .streamlit/secrets.toml with an example key (will not save secrets to repo)
- Provide the exact Task Scheduler XML or PowerShell script for import
- Start the Streamlit app locally to test the warming endpoint (requires permission)