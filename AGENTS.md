# Autonomous Project Workspace Policy

## 1. Project Boundary & Scope
- All agent operations, code inspections, executions, and file modifications are strictly bounded to this project repository (`pyEGClamUI`).
- The assistant is strictly prohibited from inspecting, creating, modifying, or accessing any file, folder, or resource outside this project directory without explicit prior permission from the user.

## 2. Blanket File Authorization Within Project
- The assistant is fully authorized to autonomously inspect, read, create, edit, update, and manage any code file, test file, documentation, or asset located within this project repository.
- Routine file inspections, code edits, package builds, and automated test runs within this project repository must proceed without prompting the user for repetitive, individual read or write confirmations.

## 3. Markdown Documentation & Visual Standards
- **Proper, Portable Relative Links**: All markdown links in documentation (`docs/*.md`) must use clean, relative paths (`../src/pyegclamui/...`, `LOGGING.md`, etc.). Never hardcode machine-specific absolute file URIs (`file:///...`).
- **Robust Mermaid & Flowchart Syntax**: Always enclose Mermaid node labels containing parentheses, brackets, or punctuation in double quotes (`["Label (Details)"]` or `{"Condition?"}`) to ensure zero parsing errors.
- **Structured Comparison Tables with Semantic Emoji**: Use comparative markdown tables with consistent colored symbols (🟢 Clean/Active, 🟡 Warning/Medium, 🔴 Danger/Critical, ⚪ Inactive, ❌ Aborted/Disallowed, ⚡ Fast/Daemon, 🛡️ Guard/Security).
- **Readable Paragraphs & Typography**: Keep paragraphs concise (2–4 sentences max) for high scannability. Use clear headings, structured bullet items with bold concepts, and GitHub-style callout alerts (`> [!NOTE]`, `> [!IMPORTANT]`, etc.).

