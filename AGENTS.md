# Instructions for AI agents

## Prompts

- Generously ask questions before implementation, especially regarding
  - the core task to be solved
  - UX decisions
- Questions are questions, not hints to implement something. Don't start making changes based on such "hints".

## Worktrees and sub-agents

- Main agent is primarily for communicating with the human, answering user questions and basic research to ask the user questions
- Use sub-agents for implementation, review and testing.
  - Only use your general agent. Don't use the sub-agents specified in this project.
- High level planning and question answering is generally better done in the main agent.
- Individual sub-agents should implement, verify results and commit in a worktree. It should then merge back to the branch that we're on currently.
- Consider doing simple tasks with a less expensive model (eg. Fable (main agent) -> Opus (sub-agent)). Don't go below Opus or gpt sol models.

## Verification

- Try to verify changes end-to-end.

## Code quality

- Notify the user if seeing clearly redundant or suboptimal files and ask for refactor
- Avoid verbose comments
- Avoid redundant tests
- This is a small project. Keep tests fast. Not everything must be tested.

## Commit discipline

- Every user requested change should be accompanied by a commit. Don't ask for permission, just do it as the last step.
  - If multiple unrelated changes are requested within one prompt, then separate commits should be created.
- Most commits should include corresponding test additions or changes.
  - There is no log for fixes, the markdown files are for the current state
- Never push unless explicitly commanded so.

## Misc

- When waiting task to finish (eg. tests etc), avoid endlessly polling for the finish
