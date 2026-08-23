# CN Mini-Project — Agent Workflow README

**Student:** Sharad K. Ghimire | **Program:** BCT, IOE Pulchowk Campus | **Course:** Computer Networks Mini-Project

## Read this before doing anything

Cisco Packet Tracer has **no official CLI/scripting API** for building topologies (placing devices, cabling, etc.).
There is no legitimate way to fully automate topology construction from a Linux shell. Third-party tools that
claim to do this (GUI-automation bots, unofficial "MCP bridges" that inject JavaScript into Packet Tracer's
webview) exist but are immature, unofficial, and in at least one documented case have had command-injection
vulnerabilities and silent-failure bugs. Do not build a grade-critical project around one of these unless you
fully understand and accept that risk.

**What an agent CAN reliably do for this project:**
1. Produce the complete network design (addressing, topology, routing plan, VLAN plan, server plan) — done in `02-network-design.md`.
2. Generate every device's IOS configuration as plain CLI text, ready to paste into Packet Tracer's CLI tab — done in `04-device-configs.md`.
3. Generate the written proposal/report content (pool of addresses, subnet table, server IPs) required for submission — done in `02-network-design.md`, formatted for direct transcription into the report.
4. Give you a step-by-step build checklist for the GUI part — done in `03-build-instructions.md`.
5. Give you a verification/testing checklist to confirm the network actually works before submission — done in `05-verification-checklist.md`.

**What an agent CANNOT reliably do:**
- Click-and-drag devices onto the Packet Tracer canvas and wire them up without either (a) you doing it manually, or (b) an unofficial/fragile automation bridge.

## File map
- `01-requirements-parsed.md` — the assignment's requirements broken into a literal checklist, so nothing is missed.
- `02-network-design.md` — the actual network design: IP plan, subnet table, topology, OSPF areas, VLANs, server placement. This is the technical core.
- `03-build-instructions.md` — step-by-step instructions for physically building the topology in Packet Tracer's GUI.
- `04-device-configs.md` — full IOS CLI configuration for every router and switch, ready to paste.
- `05-verification-checklist.md` — tests to run inside Packet Tracer to prove the network works, mapped back to requirements.
- `06-report-outline.md` — structure for the written proposal/report deliverable, pre-filled with the design's content.

## How the agent should use these files
Treat `02-network-design.md` as the single source of truth for addressing. Every other file must stay
consistent with it — if the design changes, that file changes first, and the configs/instructions get
regenerated from it, not edited independently (they will drift and break OSPF adjacencies otherwise).
