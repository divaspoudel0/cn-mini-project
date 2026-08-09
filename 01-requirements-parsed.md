# Requirements — Parsed Checklist

Source: IOE Pulchowk Campus, Computer Networks Mini-Project Proposal (July 2025 batch).

Use this file to grade the design in `02-network-design.md` against. Every box must map to something
concrete and named, not just "yes we did OSPF somewhere."

- [x] **IP address block**: at least a /22 or larger. → 10.10.0.0/21 (2046 usable hosts).
- [x] **Networks**: minimum 9 networks (LANs, not counting router-to-router P2P links), with **at least
      6 different subnet sizes** among them. → 10 LANs, sizes /24, /25, /26, /27, /28, /29.
- [x] **VLANs**: at least 3 VLANs, extended across at least 3 different switches (i.e. trunked, same VLAN
      reachable from more than one switch). → VLANs 10/20/30 on SW-ADMIN, SW-FACULTY, SW-STUDENT with
      inter-switch trunks carrying all three.
- [x] **Routers**: at least 9 routers total, of which **at least 3 have no LAN interface at all**
      (pure transit/backbone routers, only router-to-router links). → 11 routers; R1, R2, R3 have no LAN.
- [x] **Routing protocol**: OSPF for all internal routing.
  - [x] Default/Internet-bound traffic forwarded to the upstream ISP (static default route on the border
        router, redistributed into OSPF, or `default-information originate`).
  - [x] The ISP forwards traffic *into* your network using a **static route** (not dynamic routing) —
        i.e. no OSPF/BGP peering with the ISP itself.
  - [x] At least **3 OSPF areas**, including the backbone (Area 0). → Area 0/1/2.
  - [x] Follow standard good practice: passive-interface on LAN-facing ports, router-id set explicitly,
        area boundaries at ABRs, no unnecessary route redistribution loops.
- [x] **Servers**
  - [x] At least 2 DNS servers, in different LANs, doing caching + resolving your own domain's web
        records. → DNS-1 (Server-Farm), DNS-2 (DMZ).
  - [x] At least 2 Web servers, on different subnets. → WEB-1 (Server-Farm), WEB-2 (DMZ).
  - [x] One more DNS server layer sitting inside the **upstream ISP's** network, used to resolve
        addresses beyond your own domain (simulates root/public DNS). → ISP-DNS (198.51.100.2).
  - [x] DHCP: each LAN *can* have a DHCP server (interpreted as: each LAN should hand out IP,
        default gateway, and DNS server info via DHCP — use one DHCP server per LAN or a
        centralized DHCP server with `ip helper-address`/relay per LAN, either is standard practice).
- [x] **Topology**: multiple paths (redundant links) in **at least 2** of the networks/areas.
- [ ] **Header**: full name + campus roll number on the proposal document header.

## Deliverables required in the proposal
1. **Topology diagram** showing:
   - All routers, switches, PCs, servers.
   - The link to the upstream ISP.
   - Network ID of every network — LAN **and** point-to-point link.
   - Location + description of web and DNS servers.
   - Location of DHCP server(s).
2. **Written description** containing:
   - Pool of IP addresses (the overall block).
   - A table of subnets: size, IP range, network ID.
   - IP address of every server.
   - Any additional specs.
