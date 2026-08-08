# Device Configurations (IOS CLI)

Paste each block into the corresponding device's CLI tab in Packet Tracer, starting from global config
mode (`enable`, `configure terminal`). Interface numbers below (`s0/0/0`, `s0/0/1`, `g0/0`, etc.) assume
a router with 2 built-in FastEthernet/GigabitEthernet + a WIC-2T serial module added in slot 0/0 or 0/1.
**Check your actual device's interfaces in Packet Tracer and adjust numbers to match** — this is the
single most common reason a copy-pasted config fails silently.

---
## R1-CORE (no LAN — backbone only)
```
enable
configure terminal
hostname R1-CORE
!
interface Loopback0
 ip address 1.1.1.1 255.255.255.255
!
interface Serial0/0/0
 description Link-to-R2
 ip address 10.10.4.1 255.255.255.252
 clock rate 64000
 no shutdown
!
interface Serial0/0/1
 description Link-to-R3
 ip address 10.10.4.9 255.255.255.252
 no shutdown
!
interface Serial0/1/0
 description Link-to-R9-Border
 ip address 10.10.4.45 255.255.255.252
 no shutdown
!
router ospf 1
 router-id 1.1.1.1
 passive-interface default
 no passive-interface Serial0/0/0
 no passive-interface Serial0/0/1
 no passive-interface Serial0/1/0
 network 10.10.4.0 0.0.0.3 area 0
 network 10.10.4.8 0.0.0.3 area 0
 network 10.10.4.44 0.0.0.3 area 0
 network 1.1.1.1 0.0.0.0 area 0
!
end
write memory
```

---
## R2-DIST-A1 (ABR, Area 0 / Area 1 — no LAN)
```
enable
configure terminal
hostname R2-DIST-A1
!
interface Loopback0
 ip address 1.1.1.2 255.255.255.255
!
interface Serial0/0/0
 description Link-to-R1
 ip address 10.10.4.2 255.255.255.252
 no shutdown
!
interface Serial0/0/1
 description Link-to-R3
 ip address 10.10.4.5 255.255.255.252
 clock rate 64000
 no shutdown
!
interface Serial0/1/0
 description Link-to-R4
 ip address 10.10.4.13 255.255.255.252
 clock rate 64000
 no shutdown
!
interface Serial0/1/1
 description Link-to-R5
 ip address 10.10.4.17 255.255.255.252
 clock rate 64000
 no shutdown
!
interface Serial0/2/0
 description Link-to-R6
 ip address 10.10.4.21 255.255.255.252
 clock rate 64000
 no shutdown
!
router ospf 1
 router-id 1.1.1.2
 passive-interface default
 no passive-interface Serial0/0/0
 no passive-interface Serial0/0/1
 no passive-interface Serial0/1/0
 no passive-interface Serial0/1/1
 no passive-interface Serial0/2/0
 network 10.10.4.0 0.0.0.3 area 0
 network 10.10.4.4 0.0.0.3 area 0
 network 10.10.4.12 0.0.0.3 area 1
 network 10.10.4.16 0.0.0.3 area 1
 network 10.10.4.20 0.0.0.3 area 1
 network 1.1.1.2 0.0.0.0 area 0
!
end
write memory
```
`R3-DIST-A2` mirrors R2 exactly but for Area 2 (links to R7, R8) instead of Area 1 — copy the pattern,
swap addresses per the P2P table in `02-network-design.md` section 3.

---
## R4-ACC-ADMIN (Area 1 — router-on-a-stick + DHCP + LAN, template for all access routers)
```
enable
configure terminal
hostname R4-ACC-ADMIN
!
interface Loopback0
 ip address 1.1.1.4 255.255.255.255
!
interface Serial0/0/0
 description Link-to-R2
 ip address 10.10.4.14 255.255.255.252
 no shutdown
!
interface GigabitEthernet0/0
 description Trunk-to-SW-ADMIN
 no shutdown
!
interface GigabitEthernet0/0.10
 description Admin-VLAN
 encapsulation dot1Q 10
 ip address 10.10.0.129 255.255.255.128
!
interface GigabitEthernet0/1
 description Server-Farm-and-Library
 ip address 10.10.0.1 255.255.255.224
 no shutdown
!
router ospf 1
 router-id 1.1.1.4
 passive-interface default
 no passive-interface Serial0/0/0
 network 10.10.4.12 0.0.0.3 area 1
 network 10.10.0.128 0.0.0.127 area 1
 network 10.10.0.0 0.0.0.31 area 1
 network 1.1.1.4 0.0.0.0 area 1
!
ip dhcp excluded-address 10.10.0.129 10.10.0.140
ip dhcp pool ADMIN-POOL
 network 10.10.0.128 255.255.255.128
 default-router 10.10.0.129
 dns-server 10.10.0.10 10.10.0.100
!
end
write memory
```
Repeat this pattern for R5-ACC-FACULTY, R6-ACC-STUDENT, R7-ACC-ENG, R8-ACC-HOSTEL, R10-ACC-BRANCH —
swap: hostname, loopback (1.1.1.5 ... 1.1.1.10), serial IPs from the P2P table, LAN IP = the LAN's
gateway (first usable address in that subnet), OSPF area (1 for R5/R6, 2 for R7/R8/R10), and DHCP pool
network/name to match. R5 and R6 also need the extra Serial interface for the R5–R6 cross-link
(10.10.4.25/.26) added to both configs and included in their OSPF `network` statements.

---
## R9-BORDER (Area 0, DMZ LAN + ISP edge — default route origin)
```
enable
configure terminal
hostname R9-BORDER
!
interface Loopback0
 ip address 1.1.1.9 255.255.255.255
!
interface Serial0/0/0
 description Link-to-R1
 ip address 10.10.4.46 255.255.255.252
 clock rate 64000
 no shutdown
!
interface Serial0/0/1
 description Link-to-ISP
 ip address 203.0.113.1 255.255.255.248
 no shutdown
!
interface GigabitEthernet0/0
 description DMZ-LAN
 ip address 10.10.0.97 255.255.255.224
 no shutdown
!
router ospf 1
 router-id 1.1.1.9
 passive-interface default
 no passive-interface Serial0/0/0
 network 10.10.4.44 0.0.0.3 area 0
 network 10.10.0.96 0.0.0.31 area 0
 network 1.1.1.9 0.0.0.0 area 0
 default-information originate
!
ip route 0.0.0.0 0.0.0.0 203.0.113.2
!
end
write memory
```

---
## ISP-RTR (outside your OSPF domain entirely — static route only, no dynamic routing)
```
enable
configure terminal
hostname ISP-RTR
!
interface Serial0/0/0
 description Link-to-R9-Border
 ip address 203.0.113.2 255.255.255.248
 clock rate 64000
 no shutdown
!
interface GigabitEthernet0/0
 description ISP-internal-LAN-with-public-DNS
 ip address 198.51.100.1 255.255.255.240
 no shutdown
!
ip route 10.10.0.0 255.255.248.0 203.0.113.1
!
end
write memory
```
Do **not** add `router ospf` on ISP-RTR — the requirement explicitly wants static routing on the ISP
side, no dynamic protocol exchanged with your network. This is a deliberate, gradeable design choice —
mention it explicitly in the report so it reads as intentional, not an omission.

---
## SW-ADMIN (VLAN + trunk template — repeat pattern for SW-FACULTY, SW-STUDENT)
```
enable
configure terminal
hostname SW-ADMIN
!
vlan 10
 name ADMIN
vlan 20
 name FACULTY
vlan 30
 name STUDENT
!
interface GigabitEthernet0/1
 description Trunk-to-R4
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
!
interface GigabitEthernet0/2
 description Trunk-to-SW-FACULTY
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
!
interface range FastEthernet0/1-20
 switchport mode access
 switchport access vlan 10
!
end
write memory
```
SW-FACULTY: same VLANs, trunk ports toward R5 and toward SW-ADMIN, access ports default to VLAN 20.
SW-STUDENT: same VLANs, trunk port toward R6, access ports default to VLAN 30.

---
## Config checklist before you consider a device "done"
- [ ] `show ip interface brief` — every interface you intended to use shows `up/up`.
- [ ] `show ip ospf neighbor` — expected neighbors appear in `FULL` state.
- [ ] `show ip route` — routes to remote subnets appear via O (OSPF), and R9 shows the default route.
- [ ] DHCP pool's `network` statement matches the LAN's actual mask exactly — a mismatch here is the
      #1 cause of "PC gets no IP" bugs.
