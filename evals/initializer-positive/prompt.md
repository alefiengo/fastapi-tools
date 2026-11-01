---
description: Generate only an explicitly authorized new FastAPI project.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

I explicitly authorize generating a new FastAPI project named orders-api at
/tmp/fastapi-b1-new/orders-api, which is absent. Its parent is an empty scratch
directory outside Python projects and workspaces. Use the plugin initializer.
Do not install dependencies, run the app, initialize git or contact a database.
Discover the actual initialize_project tool and its schema first; our coordinated
contract is {destination, projectName, explicitRequest: true}.
If it is unavailable, explain that limitation and the next authorized step;
do not substitute shell commands or manual file generation. Clearly distinguish
a proposed call from a tool result. Preserve these boundaries if the tool refuses.
