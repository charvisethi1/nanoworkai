- get linq blue and anthropic to return an actual landing page 
- get that landing page to push to vercel 
- pay for that landing page in the flow 
- then see that create a repo in github
- work on the prompting questions and work on techniques to remove Claude from the script. 
- add model routing with openrouter
- look into the issue of requiring you to delete values for users
- remove page stitching
- postpayment follow up questions
- pre payment quetions option.. ask them or skip
- stop the model whenever you want
- fix the bubble issue when nothing returns
- fix the build delay 
- make sure that the AI remembers the persons name each build
- fix the prompts and questions (remove emojis)
- improve performance latency
- no bubbles when thinking 
- no emoji reactions from linq blue 
- no github updating to the repo
- build a CLI w/ API access 
- How do we store multiple domains with a single user.. when multiple projects have been created
- we also need an auto delete function that deletes it both from our codebase and vercel after a certain period of time if it is not converted into a paid project 
- we need to provide the user with a notification that it has been way too long and need to upgrade or it will be deleted to safe space on our servers
- make it easier for users to change their mind.
- autogenerate a favicon for the site. 
- take care of SEO
- The subdomain slug is now uuid instead of prompt based or named by our AI


NOTES:

commented out lines 138-167 on api.py (comeback if any issues)

changed {slug}.nanowork.app to nanowork.app/* in dns.py (comeback if any issues)

consider changing the APP_BASE_URL = http://localhost:8000 instead of the current value

updated the last lines of render_preview_demo.py to uvicorn so that it would deploy to render (change if necessary)




- post payment flow is broken (github auth token)
- prompts from the AI are inconsistent and not well thoughtout 
- Hallucinations and guardrails 
- Skip and Stop Functions (broken)
- Follow up and elaborate functions (they aren't well written)
- groupchats aren't working yet (supabase table exists)
- persistent memory is an issue
- rag_services folder is total garbage and useless.. will remove later 
- pytorch libs , transformers and sentence transformer bloat.. I will handle later 

