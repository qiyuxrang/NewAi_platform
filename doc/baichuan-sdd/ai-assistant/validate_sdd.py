"""Validate local SDD links, identifiers, traceability and checkpoint structure.

Run with any Python 3 interpreter. This checks documentation, not application behavior.
"""
import json
import re
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent
ERRORS = []


def refs(value, prefix):
    expanded = value
    pattern = re.escape(prefix) + r"(\d+)[—–-]" + re.escape(prefix) + r"(\d+)"
    for match in re.finditer(pattern, value):
        lower, upper = map(int, match.groups())
        expanded += " " + " ".join(f"{prefix}{n:02}" for n in range(lower, upper + 1))
    return set(re.findall(re.escape(prefix) + r"\d+", expanded))


def table_rows(filename, columns):
    for line in (PACKAGE / filename).read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if len(cells) == columns:
                yield cells


def sequential(ids, prefix):
    expected = {f"{prefix}{n:02}" for n in range(1, len(ids) + 1)}
    if set(ids) != expected or len(set(ids)) != len(ids):
        ERRORS.append(f"Non-sequential or duplicate identifiers: {prefix}")


requirements = re.findall(
    r"^### (AI-FR\d+) ", (PACKAGE / "spec.md").read_text(encoding="utf-8"), re.M
)
task_list = [row for row in table_rows("tasks.md", 5) if re.fullmatch(r"AI-T\d+", row[1])]
acceptance_list = [row for row in table_rows("acceptance.md", 4) if re.match(r"^AI-AC\d+ / ", row[0])]
tasks = {row[1]: row for row in task_list}
acceptance = {row[0].split(" / ")[0]: row for row in acceptance_list}
decision_headings = re.findall(r"^## (AI-D\d+)(?=[\s：:])",
    (PACKAGE / "decisions.md").read_text(encoding="utf-8"), re.M)
if len(set(decision_headings)) != len(decision_headings):
    ERRORS.append("Duplicate decision heading identifiers: AI-D")
sequential(requirements, "AI-FR")
sequential([row[1] for row in task_list], "AI-T")
sequential([row[0].split(" / ")[0] for row in acceptance_list], "AI-AC")

markdown = sorted(PACKAGE.rglob("*.md"))
link_count = 0
for document in markdown:
    for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
        target = link.split("#", 1)[0].strip("<>")
        if not target or re.match(r"^[a-zA-Z]+:", target):
            continue
        link_count += 1
        if not (document.parent / target).resolve().exists():
            ERRORS.append(f"Missing link: {document.relative_to(PACKAGE)} -> {target}")

for task, row in tasks.items():
    if row[0] not in {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "DONE"}:
        ERRORS.append(f"Unknown task status: {task}")
    for criterion in refs(row[4], "AI-AC"):
        if criterion not in acceptance or task not in refs(acceptance[criterion][3], "AI-T"):
            ERRORS.append(f"Non-reciprocal mapping: {task} -> {criterion}")
    for requirement in refs(row[4], "AI-FR"):
        if requirement not in requirements:
            ERRORS.append(f"Undefined requirement: {task} -> {requirement}")
    for dependency in refs(row[3], "AI-T"):
        if dependency not in tasks or dependency == task:
            ERRORS.append(f"Invalid dependency: {task} -> {dependency}")

for criterion, row in acceptance.items():
    if row[0].split(" / ")[1] not in {"NOT_RUN", "PASS", "FAIL", "BLOCKED"}:
        ERRORS.append(f"Unknown acceptance status: {criterion}")
    for task in refs(row[3], "AI-T"):
        if task not in tasks or criterion not in refs(tasks[task][4], "AI-AC"):
            ERRORS.append(f"Non-reciprocal mapping: {criterion} -> {task}")
    for requirement in refs(row[3], "AI-FR"):
        if requirement not in requirements:
            ERRORS.append(f"Undefined requirement: {criterion} -> {requirement}")

for label, rows, column in [("tasks", tasks, 4), ("acceptance", acceptance, 3)]:
    coverage = set().union(*(refs(row[column], "AI-FR") for row in rows.values()))
    for missing in set(requirements) - coverage:
        ERRORS.append(f"Requirement missing from {label}: {missing}")


def check_dependencies(task, ancestry):
    if task in ancestry:
        ERRORS.append("Dependency cycle: " + " -> ".join([*ancestry, task]))
        return
    for dependency in refs(tasks[task][3], "AI-T"):
        if dependency in tasks:
            check_dependencies(dependency, [*ancestry, task])


for task in tasks:
    check_dependencies(task, [])

checkpoint = json.loads((PACKAGE / "checkpoint.json").read_text(encoding="utf-8"))
for key in ["schema_version", "spec_version", "implementation_authorized", "implementation_status",
            "current_task", "next_task", "checks", "pending_dependencies", "resume_steps"]:
    if key not in checkpoint:
        ERRORS.append(f"Missing checkpoint key: {key}")
for key in ["current_task", "next_task"]:
    if checkpoint.get(key) is not None and checkpoint[key] not in tasks:
        ERRORS.append(f"Invalid checkpoint {key}: {checkpoint[key]}")
if checkpoint.get("implementation_status") == "not_started":
    if any(row[0] != "NOT_STARTED" for row in tasks.values()):
        ERRORS.append("Checkpoint says not started but a task has started")
    if any(row[0].split(" / ")[1] != "NOT_RUN" for row in acceptance.values()):
        ERRORS.append("Checkpoint says not started but feature acceptance has run")
for evidence in checkpoint.get("evidence_refs", []):
    if not (PACKAGE / evidence).is_file():
        ERRORS.append(f"Checkpoint references missing evidence: {evidence}")

print(json.dumps({
    "check": "documentation_only",
    "markdown_files": len(markdown),
    "local_links": link_count,
    "requirements": len(requirements),
    "tasks": len(tasks),
    "acceptance_cases": len(acceptance),
    "decision_headings": len(decision_headings),
    "errors": ERRORS,
    "status": "PASS" if not ERRORS else "FAIL",
}, ensure_ascii=False, indent=2))
raise SystemExit(bool(ERRORS))
