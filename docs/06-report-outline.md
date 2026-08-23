# Written Proposal — Outline

Header (mandatory, don't forget): **Full Name — Sharad K. Ghimire | Campus Roll Number: [FILL IN]**

## 1. Introduction
One paragraph: what network this is ("PMUN" — a fictional university with a main campus and one branch
campus), what it needs to support, why the design choices below meet the assignment's requirements.

## 2. Topology Diagram
Insert the Packet Tracer topology screenshot/export here. Must show, per the assignment's explicit list:
- All routers, switches, PCs, servers — labelled with the hostnames from `02-network-design.md` §8.
- The ISP link (R9 ↔ ISP-RTR), visually distinguished from internal links.
- Network ID labelled on every link — LAN **and** P2P (Packet Tracer lets you add text labels near cables;
  use the network IDs from `02-network-design.md` §2 and §3, don't just leave links unlabeled).
- Callouts on the diagram for where the web/DNS servers physically sit (Server-Farm and DMZ), and where
  DHCP is configured (each access router).

## 3. IP Address Pool
State the overall block: `10.10.0.0/21`, and the split into LAN space (`10.10.0.0/22`) and P2P space
(`10.10.4.0/24`), per `02-network-design.md` §1. Explain briefly *why* — cleaner documentation, easier
troubleshooting, room for growth — this is what "additional specifications / good practice" is asking for.

## 4. Subnet Table
Copy the table from `02-network-design.md` §2 (LANs) and §3 (P2P links) directly — it already has
network name, prefix, network ID, usable range, broadcast. Don't reformat it into something inconsistent
with the actual configs.

## 5. Server IP Addresses
Copy the table from `02-network-design.md` §6 directly, with one added sentence per server on its role
(caching, own-domain resolution, forwarder for outside domains, hosted web content).

## 6. Routing Design
- List routers and which have no LAN (R1, R2, R3) — state explicitly that this satisfies the
  "≥3 routers without LAN connectivity" requirement.
- Explain the 3 OSPF areas and why the boundaries are where they are (geography: main campus core vs.
  two "wings" vs. branch).
- Explain the ISP boundary explicitly: static default route out, static route in from ISP, no dynamic
  protocol across that boundary — state this is deliberate.
- Mention `passive-interface default` and explicit router-ids as "good practice" — the assignment
  literally asks you to "always prefer good practices," so naming them earns easy credit.

## 7. VLAN Design
State the 3 VLANs, which switches they're trunked across, and which router does inter-VLAN routing
(router-on-a-stick on R4/R5/R6). One sentence on why VLANs were used for Admin/Faculty/Student
specifically (traffic separation / broadcast domain control — real justification, not just "because
required").

## 8. Redundancy
Describe the two redundant paths (backbone triangle, Area 2 loop) and reference the verification test
results from `05-verification-checklist.md` (link-shutdown test) as evidence it actually works, not just
that it's drawn that way.

## 9. DHCP
State the per-router DHCP pool approach, and that servers use static IPs deliberately.

## 10. Conclusion
Short paragraph mapping each assignment requirement to a section above — makes it trivial for the grader
to check everything off, which tends to help with marks in practice.
