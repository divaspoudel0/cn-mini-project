# Build Instructions — Packet Tracer GUI

This is manual work. There is no reliable scripted shortcut for this part (see `00-README.md`). Budget
1–2 focused hours. Follow this order — cabling before configuring saves you from hunting for interfaces
that don't exist yet.

## 1. Place devices
Use Generic router (1841 or later, needs enough interfaces — check port count before placing) and
Generic 2960 switches.

- 11 routers: R1–R10 + ISP-RTR. Arrange R1/R2/R3 in a visual triangle in the middle (core), R4–R6
  around R2, R7/R8/R10 around R3, R9 + ISP-RTR off to one side (edge).
- 3 switches: SW-ADMIN, SW-FACULTY, SW-STUDENT.
- 2 servers on Server-Farm segment, 2 servers on DMZ segment, 1 server (ISP-DNS) on the ISP side.
- PCs: put at least 2–3 PCs per LAN so DHCP has something to demo. Not graded individually but makes
  the demo/viva much more convincing than empty LANs.

## 2. Interface planning (do this before cabling — avoids re-cabling later)
Each router needs: 1 interface per P2P link it's on, plus 1 interface per LAN it serves (or
sub-interfaces on one trunk interface to a switch, if you want to show 802.1Q router-on-a-stick for the
VLAN routers R4/R5/R6). Count from the design table in `02-network-design.md` section 3 and 4 before
picking a router model — an 1841 only has 2 FastEthernet + module slots, you'll likely need to add a
WIC-2T (serial) module for P2P links or just use FastEthernet for everything with straight-through/
crossover as PT auto-detects.

Recommended: use **serial links (WIC-2T module, DCE/DTE clocking)** for all P2P router-to-router links —
this is standard practice and graders expect to see serial, not Ethernet, between routers. Set clock
rate on the DCE side (Packet Tracer tells you which end is DCE when you check the cable).

## 3. Cabling order
1. R1↔R2, R2↔R3, R1↔R3 (backbone triangle) — serial.
2. R2↔R4, R2↔R5, R2↔R6, R5↔R6 (Area 1 + cross-link) — serial.
3. R3↔R7, R3↔R8, R7↔R10, R8↔R10 (Area 2 + branch redundancy) — serial.
4. R1↔R9 (border), R9↔ISP-RTR — serial for R1-R9, could use copper for R9-ISP-RTR to visually
   distinguish "your network" from "the ISP."
5. R4 → SW-ADMIN (trunk-capable link, e.g. FastEthernet), and separately R4's other interfaces to
   Server-Farm switch and Library switch (or just directly to end devices for small LANs — a /27 or /29
   LAN doesn't need its own dedicated switch, you can hang PCs straight off a small unmanaged switch or
   even directly if only 1–2 hosts, but use a switch for realism).
6. R5 → SW-FACULTY, R6 → SW-STUDENT. Also cable SW-ADMIN↔SW-FACULTY as an inter-switch trunk so VLAN 10
   genuinely extends across two switches (this is the specific thing the requirement is checking for).
7. R7, R8, R9, R10 each get a switch or direct connection to their LAN's PCs/servers as appropriate.

## 4. VLAN + trunk setup (on SW-ADMIN, SW-FACULTY, SW-STUDENT)
- Create VLAN 10 (ADMIN), VLAN 20 (FACULTY), VLAN 30 (STUDENT) on all three switches — same VLAN
  numbers/names everywhere, this matters for trunking to work sanely.
- Access ports facing PCs: `switchport mode access`, `switchport access vlan <n>`.
- Ports facing routers or other switches: `switchport mode trunk`, `switchport trunk allowed vlan
  10,20,30` (or leave default allowed-all, but explicit is better practice and worth mentioning in viva).
- On the access router facing each switch (R4/R5/R6), use **router-on-a-stick**: one physical interface,
  sub-interfaces `.10`, `.20`, `.30` with `encapsulation dot1Q <vlan>` and the LAN gateway IP for that
  VLAN.

## 5. After cabling: config
Paste the CLI blocks from `04-device-configs.md` into each device's CLI tab, one device at a time. Do
routers before switches before servers before PCs (routing has to exist before DHCP can hand out a
usable default gateway that anyone can ping through).

## 6. Server setup (GUI, not CLI)
Packet Tracer servers are configured via their Desktop/Config GUI tabs, not IOS CLI:
- DNS-1, DNS-2, ISP-DNS: Services tab → DNS → add A records per the table in `02-network-design.md`
  section 6. On DNS-1/DNS-2, add a **forwarder** pointing to 198.51.100.2 for anything not `pmun.edu.np`.
- WEB-1, WEB-2: Services tab → HTTP → enable, edit index.html so viva graders can literally load the
  page and see it's real ("Welcome to PMUN Intranet" etc. — trivial but makes the demo land).
- All servers: Desktop → IP Configuration → set static IP per the table (never DHCP for a server).

## 7. PCs
Desktop → IP Configuration → DHCP (not static) for every ordinary PC, to actually exercise the DHCP
requirement instead of just configuring it and never using it.
