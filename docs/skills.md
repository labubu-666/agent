# Skills

The agent supports Claude-style skills. A skill is a folder of instructions that the model can load when a task matches it.

## Creating a skill

Each skill is a folder containing a `SKILL.md` file. The file starts with YAML front matter between `---` lines, followed by the instructions in Markdown:

```markdown
---
name: pdf-tools
description: Extracts text and tables from PDF files. Use when the user mentions PDFs.
---

Step-by-step instructions for the agent go here.
```

The folder can also hold other files, such as reference documents or scripts. The model can read them with `read_file` or run scripts with `run_command`.

```
.claude/skills/pdf-tools/
├── SKILL.md
├── reference.md
└── scripts/
    └── extract.py
```

### Front matter fields

| Field         | Required | Rules                                                                                    |
| ------------- | -------- | ---------------------------------------------------------------------------------------- |
| `name`        | yes      | Lowercase letters, digits and hyphens, at most 64 characters.                            |
| `description` | yes      | Non-empty, at most 1024 characters. The model uses it to decide when to load the skill. |

Other fields (for example `allowed-tools`) are kept but not enforced.

## Where skills are loaded from

Skills are loaded from two folders, in priority order:

1. `<working dir>/.claude/skills/<skill>/SKILL.md` (the project). The working dir is the `--working-dir` option, or the current directory if it isn't set.
2. `~/.claude/skills/<skill>/SKILL.md` (the user).

If two skills share a name, the project one wins. Skills in parent folders are not searched.

Invalid skills are skipped, and a warning is written to the log file.

## How the agent uses skills

1. At startup, the CLI prints the skills it found, for example `Skills: pdf-tools, notes`, or `Skills: none`.
2. The system prompt lists each skill's name and description. Full instructions are not included.
3. When a task matches a skill, the model calls the `use_skill` tool with the skill's name.
4. `use_skill` returns the full `SKILL.md`, the skill's folder path and a list of its other files.

Because every skill's description is sent with each request, many skills make the prompt longer.

## Limitations

- `use_skill` does not restrict which tools the model can use after loading a skill. `allowed-tools` is not enforced.
- Only the project and user folders listed above are searched.
