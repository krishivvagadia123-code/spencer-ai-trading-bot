# Workflow Inbox

Claude, GPT, or a human operator can place incoming task drafts here.

Use Markdown or JSON task files with the same required fields as `workflow/pipeline.py`:

- objective
- files affected
- acceptance criteria
- safety rules
- test commands
- expected output

The active task should be copied or promoted to `workflow/current_task.md`.
Do not place secrets, `.env` files, broker credentials, private account data, journals,
or raw private market data in this folder.
