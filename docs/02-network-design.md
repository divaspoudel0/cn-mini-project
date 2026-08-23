# Network Design — "Pulchowk Metropolitan University Network" (PMUN)

This is the single source of truth. If you change anything here, regenerate `04-device-configs.md`
and `03-build-instructions.md` to match — do not hand-edit those independently.

## 1. Overall address pool

Allocated block: **10.10.0.0/21** (10.10.0.0 – 10.10.7.255, 2048 addresses) — larger than the
required /22, giving headroom to keep LAN and point-to-point addressing cleanly separated:

- `10.10.0.0/22` (10.10.0.0 – 10.10.3.255) → all LAN subnets.
- `10.10.4.0/24` (10.10.4.0 – 10.10.4.255) → all router-to-router point-to-point links, carved into /30s.
- `10.10.5.0/24` – `10.10.7.0/24` → reserved for future expansion (mention this in the report — shows
  good practice/foresight).

Upstream ISP network (outside your allocation, simulated): `203.0.113.0/29` for the ISP-facing link,
plus an ISP-internal LAN `198.51.100.0/28` hosting the upstream DNS resolver.

## 2. LAN subnets (10 networks, 6 distinct sizes — satisfies "≥9 networks, ≥6 sizes")

| # | Network name | VLAN | Prefix | Network ID | Usable range | Broadcast | Hosts usable |
|---|---|---|---|---|---|---|---|
| 1 | Server-Farm (Web+DNS #1) | — (native, router R9) | /27 | 10.10.0.0/27 | .1–.30 | .31 | 30 |
| 2 | Admin-LAN | VLAN 10 | /25 | 10.10.0.128/25 | .129–.254 | .255 | 126 |
| 3 | Faculty-LAN | VLAN 20 | /25 | 10.10.1.0/25 | .1–.126 | .127 | 126 |
| 4 | Student-LAN | VLAN 30 | /24 | 10.10.2.0/24 | .1–.254 | .255 | 254 |
| 5 | Library-LAN | — | /27 | 10.10.0.32/27 | .33–.62 | .63 | 30 |
| 6 | Engineering-Dept-LAN | — | /26 | 10.10.1.128/26 | .129–.190 | .191 | 62 |
| 7 | Hostel-LAN | — | /24 | 10.10.3.0/24 | .1–.254 | .255 | 254 |
| 8 | Branch-Campus-LAN | — | /28 | 10.10.0.64/28 | .65–.78 | .79 | 14 |
| 9 | DMZ-LAN (secondary DNS+Web) | — | /27 | 10.10.0.96/27 | .97–.126 | .127 | 30 |
| 10 | Guest-WiFi-LAN | — | /29 | 10.10.0.80/29 | .81–.86 | .87 | 6 |

Distinct sizes present: /24, /25, /26, /27, /28, /29 → **6 sizes**, requirement met with one to spare.

VLANs 10/20/30 are trunked across **SW-Admin, SW-Faculty, SW-Student** (three different switches) —
satisfies "≥3 VLANs extended via ≥3 switches." Put VLAN 10 also reachable from SW-Faculty via trunk
(inter-switch link) so at least one VLAN genuinely spans more than one switch, not just "exists on 3
switches independently" — that's the part graders actually check.

## 3. Point-to-point links (10.10.4.0/24, carved as /30s — not counted toward the 9 LAN networks)

| Link | Network ID | Router A | IP A | Router B | IP B |
|---|---|---|---|---|---|
| P2P-1 | 10.10.4.0/30 | R1 (Core) | .1 | R2 (Dist-A1) | .2 |
| P2P-2 | 10.10.4.4/30 | R2 (Dist-A1) | .5 | R3 (Dist-A2) | .6 |
| P2P-3 | 10.10.4.8/30 | R1 (Core) | .9 | R3 (Dist-A2) | .10 |
| P2P-4 | 10.10.4.12/30 | R2 (Dist-A1) | .13 | R4 (Admin-Acc) | .14 |
| P2P-5 | 10.10.4.16/30 | R2 (Dist-A1) | .17 | R5 (Faculty-Acc) | .18 |
| P2P-6 | 10.10.4.20/30 | R2 (Dist-A1) | .21 | R6 (Student-Acc) | .22 |
| P2P-7 | 10.10.4.24/30 | R5 (Faculty-Acc) | .25 | R6 (Student-Acc) | .26 |
| P2P-8 | 10.10.4.28/30 | R3 (Dist-A2) | .29 | R7 (Eng-Acc) | .30 |
| P2P-9 | 10.10.4.32/30 | R3 (Dist-A2) | .33 | R8 (Hostel-Acc) | .34 |
| P2P-10 | 10.10.4.36/30 | R7 (Eng-Acc) | .37 | R10 (Branch) | .38 |
| P2P-11 | 10.10.4.40/30 | R8 (Hostel-Acc) | .41 | R10 (Branch) | .42 |
| P2P-12 | 10.10.4.44/30 | R1 (Core) | .45 | R9 (Border/ISP-edge) | .46 |
| ISP-Link | 203.0.113.0/29 | R9 (Border) | .1 | ISP-Router | .2 |

Redundancy (satisfies "multiple paths in ≥2 networks"):
- **Backbone triangle**: R1–R2, R2–R3, R1–R3 (P2P-1/2/3) — Area 0 core has two independent paths
  between any two backbone routers.
- **Area 2 loop**: R7–R10 and R8–R10 (P2P-10/11), combined with R3–R7 and R3–R8 — gives Branch-Campus
  two independent paths back to the core.
- **Faculty/Student cross-link**: R5–R6 (P2P-7) gives Faculty-LAN and Student-LAN a backup path to each
  other that doesn't transit R2, useful if R2 fails.

## 4. Routers (10 total — satisfies "≥9, with ≥3 having no LAN")

| Router | Role | OSPF Area | LAN interface? |
|---|---|---|---|
| R1 | Core (backbone) | 0 | **No** |
| R2 | Distribution — Area 1 boundary | 0/1 (ABR) | **No** |
| R3 | Distribution — Area 2 boundary | 0/2 (ABR) | **No** |
| R4 | Access — Admin + Server-Farm + Library | 1 | Yes |
| R5 | Access — Faculty | 1 | Yes |
| R6 | Access — Student | 1 | Yes |
| R7 | Access — Engineering | 2 | Yes |
| R8 | Access — Hostel + Guest-WiFi | 2 | Yes |
| R9 | Border — DMZ + ISP edge | 0 | Yes |
| R10 | Access — Branch-Campus | 2 | Yes |

R1, R2, R3 have **zero LAN interfaces** — pure transit/backbone routers. Requirement satisfied exactly.

Note on LAN-to-router assignment above vs. the subnet table: R4 carries Server-Farm, Library, and
Admin-LAN (three LANs off one router is fine and realistic — a router can have multiple LAN
sub-interfaces or physical interfaces). Adjust if your topology diagram wants one LAN per router for
visual clarity; the addressing doesn't care either way, just keep `03-build-instructions.md` and
`04-device-configs.md` consistent with whatever you pick.

## 5. OSPF plan

- **3 areas**: Area 0 (backbone: R1, R2, R3, R9), Area 1 (R2, R4, R5, R6), Area 2 (R3, R7, R8, R10).
- R2 and R3 are ABRs (Area 0 + one non-backbone area each).
- `router-id` set explicitly on every router (use the loopback convention: 1.1.1.R# e.g. R1 → 1.1.1.1).
- `passive-interface default` on every router, then `no passive-interface` only on the P2P links —
  standard good practice, stops OSPF hellos leaking onto LAN segments where they serve no purpose and
  are a minor security exposure.
- R9 (border) runs a **static default route** toward the ISP (`ip route 0.0.0.0 0.0.0.0 203.0.113.2`)
  and originates it into OSPF with `default-information originate` — this is how "forward all Internet
  traffic to upstream" gets satisfied.
- The ISP router has a **static route** back into 10.10.0.0/21 via R9 (`ip route 10.10.0.0 255.255.248.0
  203.0.113.1`) — satisfies "ISP forwards to your network without dynamic routing." Do **not** run OSPF
  or any dynamic protocol between R9 and the ISP router.

## 6. Servers

| Server | Role | Location (LAN) | IP |
|---|---|---|---|
| DNS-1 | Caching + authoritative for internal domain `pmun.edu.np` | Server-Farm (10.10.0.0/27) | 10.10.0.10 |
| DNS-2 | Caching + authoritative (redundant) | DMZ-LAN (10.10.0.96/27) | 10.10.0.100 |
| WEB-1 | `www.pmun.edu.np` | Server-Farm (10.10.0.0/27) | 10.10.0.11 |
| WEB-2 | `intranet.pmun.edu.np` | DMZ-LAN (10.10.0.96/27) | 10.10.0.101 |
| ISP-DNS | Upstream/public resolver, forwards anything outside `pmun.edu.np` | ISP-internal LAN (198.51.100.0/28) | 198.51.100.2 |

DNS-1 and DNS-2 are configured to forward non-local queries to ISP-DNS (198.51.100.2) — this is the
"additional level of DNS server in the upstream ISP's network" requirement.

## 7. DHCP

One DHCP server per access router (simplest, most defensible in a viva): configure DHCP pools **directly
on each access router** (R4–R10) using Cisco IOS's built-in DHCP server feature, one pool per attached
LAN, each pool handing out: correct network/mask, `default-router` (the router's own LAN interface IP,
always the first usable address), and `dns-server` (10.10.0.10 primary, 10.10.0.100 secondary).
Server-Farm and DMZ-LAN themselves use **static IPs**, not DHCP (servers should never get dynamic addresses).

If you want to show `ip helper-address` / relay knowledge instead (slightly more advanced, worth
mentioning even if you don't implement it everywhere): centralize DHCP on R4 and relay from R5–R10 via
`ip helper-address 10.10.4.14` on each of their LAN interfaces. Pick one approach and be consistent —
don't mix without saying why in the report.

## 8. Naming/documentation conventions for the agent to follow everywhere
- Router hostnames: `R1-CORE`, `R2-DIST-A1`, `R3-DIST-A2`, `R4-ACC-ADMIN`, `R5-ACC-FACULTY`,
  `R6-ACC-STUDENT`, `R7-ACC-ENG`, `R8-ACC-HOSTEL`, `R9-BORDER`, `R10-ACC-BRANCH`, `ISP-RTR`.
- Switch hostnames: `SW-ADMIN`, `SW-FACULTY`, `SW-STUDENT`.
- Loopback0 on every internal router = `1.1.1.R#/32` (used as OSPF router-id, also good practice for
  stable router-id even if a physical interface flaps).
