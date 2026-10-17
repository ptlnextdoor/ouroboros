# FORGE Makefile. PY points at the interpreter that has cadquery + the Crusoe deps.
PY ?= /opt/miniconda3/bin/python3
export FREECAD_BIN ?= /Applications/FreeCAD.app/Contents/Resources/bin
TASK ?= br02
PLAYBOOK ?= playbook/v0.md

.PHONY: selftest verify-isolation demo nplus1 heldout tasks ui

## blocks + referee physics + llm price-math/dry-run
selftest:
	$(PY) -m forge.blocks
	$(PY) -m referee.referee --selftest
	$(PY) -m forge.llm --dry-run

## regenerate the 16 tasks + hidden cases + feasibility evidence
tasks:
	$(PY) tasks/build_tasks.py

## one task, end to end (TASK=br0X PLAYBOOK=playbook/vN.md)
demo:
	$(PY) -m forge.loop --task $(TASK) --playbook $(PLAYBOOK) --budget 1.0

## stage UI: http://localhost:8008/ (live tail of newest run)  ·  /?replay=ui/fixture/br02 (zero-network fallback)
ui:
	python3 ui/serve.py

## Version N+1: edit the playbook, gate kept edits on DEV
nplus1:
	$(PY) -m forge.gate --rounds 3

## final heldout A/B (A=playbook/v0.md B=playbook/vN.md)
A ?= playbook/v0.md
B ?= playbook/v1.md
heldout:
	$(PY) -m forge.gate --heldout --playbook-a $(A) --playbook-b $(B)

## isolation guard: nothing in forge/ may read the hidden cases except via the
## referee.evaluate call path in loop.py, and agent prompts must never contain a
## hidden case name. Fails (exit 1) on any violation.
verify-isolation:
	@echo "== forge/ must not read referee/hidden or import hidden_cases (except loop.py's referee step) =="
	@bad=0; \
	for f in forge/llm.py forge/agents.py forge/gate.py; do \
	  if grep -nE "referee/hidden|hidden_cases|/hidden/" $$f >/dev/null 2>&1; then \
	    echo "VIOLATION: $$f references the hidden set"; bad=1; \
	  fi; \
	done; \
	if grep -nE "referee/hidden|hidden\.json|open\(.*hidden" forge/agents.py >/dev/null 2>&1; then \
	  echo "VIOLATION: agents.py touches hidden files"; bad=1; \
	fi; \
	echo "-- loop.py may only reach hidden via referee.hidden_cases in referee_cases() --"; \
	hits=$$(grep -nE "hidden_cases|referee/hidden" forge/loop.py | grep -v "referee.hidden_cases(task" | grep -vE "^\s*#" | grep -viE "hidden set|referee-only|only this file" || true); \
	if [ -n "$$hits" ]; then echo "VIOLATION in loop.py:"; echo "$$hits"; bad=1; fi; \
	echo "== agent prompts must never contain a hidden case name =="; \
	names=$$($(PY) -c "import json,glob,os; ns=set(); [ns.update(c['name'] for c in json.load(open(p))) for p in glob.glob('referee/hidden/*.json')]; print(' '.join(sorted(ns)))"); \
	echo "hidden case names: $$names"; \
	for n in $$names; do \
	  if grep -nF "$$n" forge/agents.py >/dev/null 2>&1; then \
	    echo "VIOLATION: agents.py prompt contains hidden case name '$$n'"; bad=1; \
	  fi; \
	done; \
	if [ $$bad -ne 0 ]; then echo "ISOLATION CHECK FAILED"; exit 1; fi; \
	echo "ISOLATION CHECK PASSED"
